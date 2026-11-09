# Change log

## Kernel cleanup safety fix

This change is recorded as one commit: **Protect running and Raspberry Pi kernels during cleanup**. It updates the script, usage documentation, and regression tests together so the safety behavior and its tests remain in sync.

### Why this change was needed

The old script could list the unversioned `raspberrypi-kernel` bundle for removal even when it supplied the running kernel. It also ran unrestricted `apt-get autoremove`, which could remove packages outside the displayed selection.

### Changes

- Preserve legacy Raspberry Pi kernel and header bundles.
- Require an exact installed versioned-image match for the running kernel before allowing cleanup.
- Preserve held packages, validate selection numbers, and match headers exactly.
- Add `--dry-run` and simulate the whole APT transaction before making changes.
- Reject unexpected removals, installations, configuration actions, ambiguous package identities, and incomplete plans.
- Remove unrestricted autoremove, require interactive confirmation, show APT errors, and stop on failures.

### Verification

- `bash -n debian-kernel-clean.sh` passed.
- `python3 -m unittest discover -s tests -v` passed all 28 tests.
- Patch applicability was checked against upstream commit `a4693a81037af7e3dd1a795cb0b6f43d15efd27f`.
- Tests used isolated command mocks. No real packages or bootloader files were changed.
- ShellCheck was unavailable. Live Debian, Ubuntu, and Raspberry Pi OS testing has not been performed.

### Remaining precautions

Keep a known-good fallback kernel when choosing removals. Legacy unversioned Raspberry Pi packages are deliberately not removable through this script. Shared/common headers and separately packaged modules are retained. Avoid concurrent package-manager operations and review APT's final removal list, because simulation and execution are separate transactions.

## Git terms used for this change

- A **commit** is a saved set of changes with an explanation.
- A **branch** keeps a proposed change separate from the main version.
- A **push** publishes commits and a branch to GitHub.
- A **merge** brings a branch's changes into another branch, usually `main`. Publishing a fix branch alone does not change `main`.
