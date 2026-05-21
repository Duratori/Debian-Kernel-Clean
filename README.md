# Debian Kernel Clean

An interactive shell script that removes old, unused kernel packages on any Debian-based Linux system.

Inspired by the [Proxmox VE kernel-clean](https://github.com/community-scripts/ProxmoxVE/blob/main/tools/pve/kernel-clean.sh) tool from [community-scripts](https://github.com/community-scripts/ProxmoxVE), adapted to work on any Debian or Ubuntu system.

## Features

- Detects the currently running kernel and lists all other installed kernel packages
- Interactive numbered menu — select which kernels to remove (comma-separated)
- Automatically finds and removes matching `linux-headers-*` packages
- Runs `apt-get autoremove` and `update-grub` (when available) after cleanup
- Raspberry Pi compatible — detects `raspberrypi-kernel` packages and gracefully skips GRUB on systems that don't use it
- Color-coded output for clear status reporting

## Usage

```bash
sudo bash debian-kernel-clean.sh
```

Or make it executable first:

```bash
chmod +x debian-kernel-clean.sh
sudo ./debian-kernel-clean.sh
```

> **Note:** Must be run as root — the script will exit with an error if not.

## Requirements

- Any Debian-based Linux distribution (Debian, Ubuntu, Linux Mint, Pop!_OS, Raspberry Pi OS, etc.)
- `bash`, `dpkg`, `apt-get`
- `update-grub` (optional — skipped automatically on systems without GRUB, such as Raspberry Pi)

## How It Works

1. Identifies the currently running kernel via `uname -r`
2. Lists all installed `linux-image-*` and `raspberrypi-kernel` packages except the running one
3. Prompts you to select which kernels to remove
4. Shows a confirmation with all packages (images + headers) to be purged
5. Removes selected packages and runs cleanup

## Raspberry Pi Notes

- **Standard Debian on Pi**: Works out of the box — kernel packages follow the `linux-image-*` naming convention.
- **Raspberry Pi OS**: Detects `raspberrypi-kernel` and `raspberrypi-kernel-headers` packages.
- GRUB update is skipped automatically since Raspberry Pi uses its own bootloader.

## License

MIT
