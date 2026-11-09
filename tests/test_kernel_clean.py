"""Non-destructive integration tests: every system-changing command is a fake."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "debian-kernel-clean.sh"
BASH = shutil.which("bash")
SORT = shutil.which("sort")


def pkg(name, arch="amd64", status="ii "):
    return f"{status}\t{name}\t{arch}\n"


CURRENT = "6.1.0-20-amd64"
OLD = "6.1.0-19-amd64"
BASE = (
    pkg(f"linux-image-{CURRENT}")
    + pkg(f"linux-headers-{CURRENT}")
    + pkg(f"linux-image-{OLD}")
    + pkg(f"linux-headers-{OLD}")
)
IMAGE = f"linux-image-{OLD}:amd64"
HEADER = f"linux-headers-{OLD}:amd64"

FAKE = r'''
import json
import os
from pathlib import Path
import sys

command = Path(sys.argv[0]).name
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([command, *sys.argv[1:]]) + "\n")
if command == "uname":
    print(os.environ["RUNNING_KERNEL"])
elif command == "dpkg-query":
    sys.stdout.write(os.environ["INVENTORY"])
    sys.exit(int(os.environ.get("QUERY_STATUS", "0")))
elif command == "apt-get":
    if "--simulate" in sys.argv:
        if "APT_PLAN" in os.environ:
            print(os.environ["APT_PLAN"])
        else:
            for package in sys.argv[sys.argv.index("--") + 1:]:
                print("Purg", package, "[1.0]")
        sys.exit(int(os.environ.get("SIMULATION_STATUS", "0")))
    print("Mock purge: no system changes")
    sys.exit(int(os.environ.get("PURGE_STATUS", "0")))
elif command == "update-grub":
    print("Mock GRUB update: no system changes")
    sys.exit(int(os.environ.get("GRUB_STATUS", "0")))
else:
    raise RuntimeError(command)
'''


class CleanupTests(unittest.TestCase):
    def run_script(self, selection="1\n", *, inventory=BASE, current=CURRENT,
                   dry_run=True, grub=True, args=None, override_root=True,
                   **scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            commands = ["uname", "dpkg-query", "apt-get"]
            if grub:
                commands.append("update-grub")
            for command in commands:
                path = bin_dir / command
                path.write_text(f"#!{sys.executable}\n" + FAKE)
                path.chmod(0o755)
            (bin_dir / "sort").symlink_to(SORT)
            (bin_dir / "cat").symlink_to(shutil.which("cat"))
            # PATH is deliberately isolated: the real package manager and
            # bootloader tools cannot be found, even if a mock is missing.
            env = dict(os.environ, PATH=str(bin_dir), CALL_LOG=str(root / "calls"),
                       RUNNING_KERNEL=current, INVENTORY=inventory, **scenario)
            if args is None:
                args = ["--dry-run"] if dry_run else []
            if not dry_run and override_root:
                # Exercise the mutating branch as an unprivileged user, but
                # all external commands still resolve to the fakes above.
                command = [BASH, "-c", 'source "$1"; require_root() { return 0; }; main "${@:2}"',
                           "test", str(SCRIPT), *args]
            else:
                command = [BASH, str(SCRIPT), *args]
            result = subprocess.run(command, input=selection, text=True,
                                    capture_output=True, env=env, timeout=10)
            calls = ([json.loads(line) for line in (root / "calls").read_text().splitlines()]
                     if (root / "calls").exists() else [])
            return result, calls

    @staticmethod
    def apt_calls(calls):
        return [call for call in calls if call[0] == "apt-get"]

    def test_dry_run_exact_images_and_headers_only(self):
        inventory = BASE + pkg("linux-image-amd64") + pkg("linux-headers-amd64")
        inventory += pkg(f"linux-headers-{OLD}-extra") + pkg("linux-headers-6.1.0-19-common")
        result, calls = self.run_script(inventory=inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        apt = self.apt_calls(calls)
        self.assertEqual(apt, [["apt-get", "--simulate", "--no-auto-remove", "purge", "--", IMAGE, HEADER]])
        self.assertNotIn("update-grub", [call[0] for call in calls])
        self.assertIn("No packages or bootloader files were changed", result.stdout)

    def test_legacy_pi_bundle_fails_closed(self):
        inventory = pkg("raspberrypi-kernel", "armhf") + pkg("raspberrypi-kernel-headers", "armhf")
        result, calls = self.run_script(inventory=inventory, current="6.1.21-v7+")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing cleanup", result.stderr)
        self.assertFalse(self.apt_calls(calls))

    def test_legacy_pi_bundles_never_offered_on_versioned_system(self):
        inventory = BASE + pkg("raspberrypi-kernel") + pkg("raspberrypi-kernel-headers")
        result, calls = self.run_script(inventory=inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("raspberrypi", result.stdout)
        self.assertEqual(self.apt_calls(calls)[0][-2:], [IMAGE, HEADER])

    def test_modern_pi_versioned_kernels(self):
        current = "6.12.47+rpt-rpi-v8"
        old = "6.12.34+rpt-rpi-v8"
        inventory = pkg(f"linux-image-{current}", "arm64") + pkg(f"linux-image-{old}", "arm64")
        inventory += pkg(f"linux-headers-{old}", "arm64") + pkg("linux-image-rpi-v8", "arm64")
        result, calls = self.run_script(inventory=inventory, current=current)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apt_calls(calls)[0][-2:],
                         [f"linux-image-{old}:arm64", f"linux-headers-{old}:arm64"])

    def test_unsigned_images_match_running_release(self):
        inventory = BASE.replace("linux-image-", "linux-image-unsigned-")
        result, calls = self.run_script(inventory=inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apt_calls(calls)[0][-2:], [IMAGE.replace("linux-image-", "linux-image-unsigned-"), HEADER])

    def test_current_release_is_literal_not_regex(self):
        current = "6.1.0-20-amd64"
        other = "6x1x0-20-amd64"
        inventory = pkg(f"linux-image-{current}") + pkg(f"linux-image-{other}")
        result, calls = self.run_script(inventory=inventory, current=current)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apt_calls(calls)[0][-1], f"linux-image-{other}:amd64")

    def test_missing_running_image_refuses_cleanup(self):
        result, calls = self.run_script(current="custom-kernel")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.apt_calls(calls))

    def test_no_candidates_exits_cleanly(self):
        result, calls = self.run_script(inventory=pkg(f"linux-image-{CURRENT}"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No removable", result.stdout)
        self.assertFalse(self.apt_calls(calls))

    def test_held_running_kernel_is_recognized_and_other_held_images_are_kept(self):
        inventory = pkg(f"linux-image-{CURRENT}", status="hi ") + pkg(f"linux-image-{OLD}", status="hi ")
        result, calls = self.run_script(inventory=inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.apt_calls(calls))

    def test_held_headers_and_residual_config_are_kept(self):
        inventory = pkg(f"linux-image-{CURRENT}") + pkg(f"linux-image-{OLD}")
        inventory += pkg(f"linux-headers-{OLD}", status="hi ") + pkg("linux-image-6.1.0-18-amd64", status="rc ")
        result, calls = self.run_script(inventory=inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apt_calls(calls)[0][-1], IMAGE)
        self.assertNotIn(HEADER, self.apt_calls(calls)[0])

    def test_invalid_selection_aborts_entire_request(self):
        for selection in ["0", "2", "-1", "1;echo bad", "1,2", "1,", ",1", "1,,1", "1 1", "1e", "9" * 80]:
            with self.subTest(selection=selection):
                result, calls = self.run_script(selection + "\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.apt_calls(calls))

    def test_blank_or_eof_cancels(self):
        for selection in ["", "\n", " \t\n"]:
            with self.subTest(selection=selection):
                result, calls = self.run_script(selection)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(self.apt_calls(calls))

    def test_duplicate_selection_and_leading_zero(self):
        result, calls = self.run_script("01, 1,01\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apt_calls(calls)[0][-2:], [IMAGE, HEADER])
        self.assertEqual(len(self.apt_calls(calls)[0]), 7)

    def test_package_query_failure_stops(self):
        result, calls = self.run_script(QUERY_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.apt_calls(calls))

    def test_simulation_failure_stops(self):
        result, calls = self.run_script("1\ny\n", dry_run=False, SIMULATION_STATUS="100")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.apt_calls(calls)), 1)
        self.assertNotIn("update-grub", [call[0] for call in calls])

    def test_unselected_dependency_or_running_kernel_removal_stops(self):
        for other in [f"linux-image-{CURRENT}", "linux-image-amd64", "unrelated-package", f"linux-headers-{CURRENT}"]:
            with self.subTest(other=other):
                plan = f"Purg {IMAGE} [1]\nPurg {HEADER} [1]\nRemv {other} [1]"
                result, calls = self.run_script("1\ny\n", dry_run=False, APT_PLAN=plan)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue("Refusing unselected removals" in result.stderr or "Cannot uniquely identify" in result.stderr)
                self.assertEqual(len(self.apt_calls(calls)), 1)

    def test_install_or_configure_side_effect_stops(self):
        for action in ["Inst", "Conf"]:
            result, calls = self.run_script("1\ny\n", dry_run=False,
                                            APT_PLAN=f"Purg {IMAGE}\nPurg {HEADER}\n{action} other-package")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(self.apt_calls(calls)), 1)

    def test_empty_or_incomplete_plan_stops(self):
        for plan in ["", "0 to remove", f"Purg {IMAGE}"]:
            result, calls = self.run_script("1\ny\n", dry_run=False, APT_PLAN=plan)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(self.apt_calls(calls)), 1)

    def test_simulation_architecture_can_be_omitted(self):
        plan = f"Purg {IMAGE.split(':')[0]} [1]\nPurg {HEADER.split(':')[0]} [1]"
        result, _ = self.run_script(APT_PLAN=plan)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ambiguous_multiarch_plan_is_rejected(self):
        inventory = BASE + pkg(f"linux-image-{OLD}", "arm64")
        plan = f"Purg {IMAGE.split(':')[0]} [1]\nPurg {HEADER} [1]"
        result, calls = self.run_script("1\ny\n", inventory=inventory, dry_run=False, APT_PLAN=plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot uniquely identify", result.stderr)
        self.assertEqual(len(self.apt_calls(calls)), 1)

    def test_qualified_multiarch_plan_is_accepted(self):
        inventory = BASE + pkg(f"linux-image-{OLD}", "arm64")
        result, calls = self.run_script(inventory=inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apt_calls(calls)[0][-2:], [IMAGE, HEADER])

    def test_confirmation_no_or_eof_stops_before_purge(self):
        for selection in ["1\nn\n", "1\n"]:
            result, calls = self.run_script(selection, dry_run=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(self.apt_calls(calls)), 1)
            self.assertNotIn("update-grub", [call[0] for call in calls])

    def test_confirmed_mock_purge_is_one_transaction_without_autoremove_or_yes(self):
        result, calls = self.run_script("1\ny\n", dry_run=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        apt = self.apt_calls(calls)
        self.assertEqual(apt[1], ["apt-get", "-o", "quiet=0", "-o", "APT::Get::Assume-Yes=false", "-o", "APT::Get::force-yes=false", "--no-auto-remove", "purge", "--", IMAGE, HEADER])
        self.assertEqual(len(apt), 2)
        self.assertEqual(calls[-1], ["update-grub"])

    def test_purge_failure_is_visible_and_stops_before_grub(self):
        result, calls = self.run_script("1\ny\n", dry_run=False, PURGE_STATUS="100")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("APT purge failed", result.stderr)
        self.assertNotIn("update-grub", [call[0] for call in calls])

    def test_grub_failure_is_visible(self):
        result, _ = self.run_script("1\ny\n", dry_run=False, GRUB_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GRUB update failed", result.stderr)

    def test_no_grub_is_supported(self):
        result, calls = self.run_script("1\ny\n", dry_run=False, grub=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped", result.stdout)
        self.assertEqual(len(self.apt_calls(calls)), 2)

    def test_help_and_unknown_options_never_query_packages(self):
        result, calls = self.run_script(args=["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertFalse(calls)
        result, calls = self.run_script(args=["--bad-option"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(calls)

    @unittest.skipIf(os.geteuid() == 0, "Needs a non-root test process")
    def test_mutation_requires_root(self):
        result, calls = self.run_script(dry_run=False, override_root=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Run as root", result.stderr)
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
