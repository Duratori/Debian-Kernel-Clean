#!/usr/bin/env bash
# Debian Kernel Cleanup Script
# Removes old/unused kernel packages on any Debian-based system.
# Based on: https://github.com/community-scripts/ProxmoxVE/blob/main/tools/pve/kernel-clean.sh

set -euo pipefail

function header_info {
  clear
  cat <<"EOF"
   __ __              __   ________
  / //_/__ _________ ___ / / / ____/ /__ ____ _____
 / ,< / _ \/ ___/ __ \/ _ \/ / / /   / / _ \/ __ `/ __ \
/ /| /  __/ /  / / / /  __/ / / /___/ /  __/ /_/ / / / /
/_/ |_\___/_/  /_/ /_/\___/_/  \____/_/\___/\__,_/_/ /_/
                                        [Debian Edition]
EOF
}

# Color variables
YW="\033[33m"
GN="\033[1;92m"
RD="\033[01;31m"
CL="\033[m"

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo -e "${RD}This script must be run as root.${CL}"
  exit 1
fi

# Detect current kernel
current_kernel=$(uname -r)

# Find installed kernel image packages, excluding the currently running kernel.
# Matches linux-image-<version> (standard Debian) and raspberrypi-kernel-<version> (Raspberry Pi OS).
available_kernels=$(dpkg --list | awk '/^ii[ \t]+(linux-image-[0-9]|raspberrypi-kernel[ \t])/{print $2}' | grep -v "$current_kernel" | sort -V || true)

# Also find matching linux-headers packages for later cleanup
available_headers=$(dpkg --list | awk '/^ii[ \t]+(linux-headers-[0-9]|raspberrypi-kernel-headers)/{print $2}' | grep -v "$current_kernel" | sort -V || true)

header_info

if [ -z "$available_kernels" ]; then
  echo -e "${GN}No old kernels detected. Current kernel: ${current_kernel}${CL}"
  exit 0
fi

echo -e "${GN}Currently running kernel: ${current_kernel}${CL}"
echo -e "${YW}Available kernels for removal:${CL}"
echo "$available_kernels" | nl -w 2 -s '. '

echo -e "\n${YW}Select kernels to remove (comma-separated, e.g., 1,2):${CL}"
read -r selected

# Parse selection
IFS=',' read -r -a selected_indices <<<"$selected"
kernels_to_remove=()

for index in "${selected_indices[@]}"; do
  index=$(echo "$index" | tr -d '[:space:]')
  kernel=$(echo "$available_kernels" | sed -n "${index}p")
  if [ -n "$kernel" ]; then
    kernels_to_remove+=("$kernel")
  fi
done

if [ ${#kernels_to_remove[@]} -eq 0 ]; then
  echo -e "${RD}No valid selection made. Exiting.${CL}"
  exit 0
fi

# For each selected kernel image, find its matching headers package
packages_to_remove=()
for kernel in "${kernels_to_remove[@]}"; do
  packages_to_remove+=("$kernel")
  # Extract version string from linux-image-<version> to match linux-headers-<version>
  version="${kernel#linux-image-}"
  matching_headers=$(echo "$available_headers" | grep "$version" || true)
  if [ -n "$matching_headers" ]; then
    while IFS= read -r hdr; do
      packages_to_remove+=("$hdr")
    done <<<"$matching_headers"
  fi
done

# Confirm removal
echo -e "${YW}Packages to be removed:${CL}"
printf "  %s\n" "${packages_to_remove[@]}"
read -rp "Proceed with removal? (y/n): " confirm
if [[ "$confirm" != "y" ]]; then
  echo -e "${RD}Aborted.${CL}"
  exit 0
fi

# Remove packages
for pkg in "${packages_to_remove[@]}"; do
  echo -e "${YW}Removing ${pkg}...${CL}"
  if apt-get purge -y "$pkg" >/dev/null 2>&1; then
    echo -e "${GN}Successfully removed: ${pkg}${CL}"
  else
    echo -e "${RD}Failed to remove: ${pkg}. Check dependencies.${CL}"
  fi
done

# Clean up and update bootloader
echo -e "${YW}Cleaning up...${CL}"
apt-get autoremove -y >/dev/null 2>&1
if command -v update-grub &>/dev/null; then
  update-grub >/dev/null 2>&1
  echo -e "${GN}Cleanup and GRUB update complete.${CL}"
else
  echo -e "${GN}Cleanup complete. (No GRUB detected — skipped bootloader update.)${CL}"
fi
