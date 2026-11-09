# Debian Kernel Clean

An interactive Bash script for conservatively removing selected, versioned kernel packages on Debian-based systems.

Inspired by the [Proxmox VE kernel-clean](https://github.com/community-scripts/ProxmoxVE/blob/main/tools/pve/kernel-clean.sh) tool from [community-scripts](https://github.com/community-scripts/ProxmoxVE).

## Safety behavior

- Matches the running release from `uname -r` **exactly**, rather than as a regular expression.
- Refuses cleanup if no fully installed, versioned kernel image matches the running release. This includes unsupported legacy Raspberry Pi layouts, custom kernels, and many containers or chroots.
- Never offers the running image, held packages, kernel metapackages, or unversioned `raspberrypi-kernel` packages.
- Supports Debian-style `linux-image-<release>` and Ubuntu `linux-image-unsigned-<release>` packages.
- Includes only an installed, non-held `linux-headers-<release>` package with the exact same release and architecture as a selected image. Shared/common headers and separately packaged modules are left alone.
- Validates menu numbers, rejects an invalid selection in full, and removes duplicate selections.
- Simulates the complete APT transaction first. Unexpected dependency removals, installs, configuration actions, ambiguous package identities, and incomplete plans stop cleanup.
- Purges the selected packages in one transaction, with visible output and APT's final confirmation. It explicitly disables APT's quiet, assume-yes, and force-yes settings.
- Does **not** run `apt-get autoremove`. It does not automatically select or protect a fallback kernel; keep a known-good fallback when choosing packages.
- Runs `update-grub` only after a successful purge, if that command exists. Errors are reported and stop the script.

## Usage

Preview first. This does not require root and only runs an APT simulation:

```bash
bash debian-kernel-clean.sh --dry-run
```

Then, if the proposed selection is appropriate, run interactively as root:

```bash
sudo bash debian-kernel-clean.sh
```

Choose comma-separated menu numbers, review the simulation, and confirm whether to continue to APT. Review APT's final removal list before accepting its prompt. Blank input or EOF cancels.

The simulation and real purge are separate transactions. Do not run another package manager concurrently. The script does not verify bootloader entries, package file integrity, or whether another installed kernel will boot. Package-maintainer hooks may update boot files during an actual purge.

## Raspberry Pi notes

- **Modern Raspberry Pi OS and Debian on Pi:** Versioned packages such as `linux-image-6.12.47+rpt-rpi-v8` are supported when the running release can be matched exactly.
- **Legacy Raspberry Pi OS:** `raspberrypi-kernel` and `raspberrypi-kernel-headers` are unversioned bundles, not separately removable old kernel versions. They are deliberately preserved. If they supply the running kernel and no versioned image matches, cleanup refuses to proceed.
- GRUB regeneration is skipped when `update-grub` is unavailable. No Raspberry Pi bootloader changes are performed directly by this script.

## Requirements

- A Debian-based distribution with supported, versioned kernel image packages
- Bash 4 or later, `dpkg-query`, `apt-get`, `uname`, `sort`, and `cat`
- Root for actual removal; no root needed for `--dry-run`
- `update-grub` is optional

## Tests

The regression suite uses only the Python standard library and command mocks. Its isolated `PATH` prevents access to the real package manager or bootloader tools. Mutation-path tests override only the script's root check and invoke fake commands, so the suite does not require root or change packages.

```bash
bash -n debian-kernel-clean.sh
python3 -m unittest discover -s tests -v
```

Coverage includes legacy and modern Pi kernels, signed/unsigned images, exact matching, held packages, multiarch ambiguity, invalid and duplicate selections, cancellation, simulation failures, unexpected APT actions, purge failures, and optional/failed GRUB updates. These mocks do not replace testing on representative Debian, Ubuntu, and Raspberry Pi OS installations.

## License

MIT
