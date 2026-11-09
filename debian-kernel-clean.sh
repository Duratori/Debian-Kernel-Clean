#!/usr/bin/env bash
# Conservatively remove selected, versioned Debian/Ubuntu kernel packages.
# Inspired by community-scripts/ProxmoxVE's kernel-clean.sh.

set -euo pipefail
export LC_ALL=C

usage() {
  cat <<'USAGE'
Usage: debian-kernel-clean.sh [--dry-run]

Interactively select versioned kernel images and their exact matching headers.
The running kernel, held packages, metapackages, and legacy unversioned
Raspberry Pi kernel packages are never offered for removal.

  --dry-run  Show and simulate the selection without changing the system.
  -h, --help Show this help.
USAGE
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  return 1
}

require_root() {
  [[ $EUID -eq 0 ]] || fail 'Run as root, or use --dry-run to preview safely.'
}

# Only versioned image package names have a release that can be compared with
# uname -r. In particular, raspberrypi-kernel is NOT an old kernel version.
image_release() {
  local name=${1%%:*}
  # linux-image-unsigned-<release> is used by Ubuntu.
  if [[ $name == linux-image-unsigned-[0-9]* ]]; then
    printf '%s\n' "${name#linux-image-unsigned-}"
  elif [[ $name == linux-image-[0-9]* ]]; then
    printf '%s\n' "${name#linux-image-}"
  else
    return 1
  fi
}

collect_packages() {
  local inventory status name arch package release running_found=false
  current_kernel=$(uname -r) || return
  [[ -n $current_kernel ]] || { fail 'Cannot identify the running kernel.'; return 1; }
  inventory=$(dpkg-query -W -f='${db:Status-Abbrev}\t${Package}\t${Architecture}\n') || {
    fail 'Cannot read installed packages. No changes made.'; return 1;
  }

  installed=()
  known_packages=()
  candidates=()
  while IFS=$'\t' read -r status name arch; do
    [[ -n $name && -n $arch ]] || continue
    known_packages["$name:$arch"]=1
    # Include held packages when identifying the running image, but never as
    # removal candidates. Ignore residual config and incomplete/error states.
    [[ ${status:1:2} == 'i ' && -n $name && -n $arch ]] || continue
    package="$name:$arch"
    installed["$package"]=$status
    if release=$(image_release "$name"); then
      if [[ $release == "$current_kernel" ]]; then
        running_found=true
      elif [[ $status == 'ii ' ]]; then
        candidates+=("$package")
      fi
    fi
  done <<<"$inventory"

  # Fail closed for legacy Pi bundles, custom kernels, containers/chroots, or
  # any other case where package names cannot identify the running image.
  if [[ $running_found != true ]]; then
    fail "No installed versioned image matches running kernel $current_kernel. Refusing cleanup."
    printf '%s\n' 'Legacy raspberrypi-kernel packages are deliberately preserved.' >&2
    return 1
  fi
  if ((${#candidates[@]})); then
    mapfile -t candidates < <(printf '%s\n' "${candidates[@]}" | sort -V)
  fi
}

select_packages() {
  local selected index number package release arch header
  local -a indices=()
  local -A seen=()
  packages_to_remove=()
  printf '\nSelect kernels to remove (comma-separated, e.g., 1,2; blank to cancel): '
  if ! read -r selected || [[ $selected =~ ^[[:space:]]*$ ]]; then
    return 0
  fi
  if [[ ! $selected =~ ^[[:space:]]*[0-9]+[[:space:]]*(,[[:space:]]*[0-9]+[[:space:]]*)*$ ]]; then
    fail 'Invalid selection. Enter only comma-separated menu numbers.'; return 1
  fi
  IFS=',' read -r -a indices <<<"$selected"
  for index in "${indices[@]}"; do
    number=${index//[[:space:]]/}
    if ((${#number} > 9)); then
      fail 'Selection number is too large.'; return 1
    fi
    number=$((10#$number))
    if ((number < 1 || number > ${#candidates[@]})); then
      fail "Menu number $number is out of range."; return 1
    fi
    package=${candidates[number-1]}
    [[ -z ${seen[$package]+present} ]] || continue
    seen["$package"]=1
    packages_to_remove+=("$package")
    release=$(image_release "$package") || return
    arch=${package##*:}
    header="linux-headers-$release:$arch"
    # Do not guess shared/common headers or use regex/substring matching.
    if [[ ${installed[$header]-} == 'ii ' && -z ${seen[$header]+present} ]]; then
      seen["$header"]=1
      packages_to_remove+=("$header")
    fi
  done
}

simulate_removal() {
  local plan action package rest approved target found resolved matches known
  local -A planned=()
  if ! plan=$(apt-get --simulate --no-auto-remove purge -- "${packages_to_remove[@]}" 2>&1); then
    printf '%s\n' "$plan" >&2
    fail 'APT simulation failed. No changes made.'; return 1
  fi
  printf '\nAPT simulation:\n%s\n' "$plan"
  while read -r action package rest; do
    case $action in
      Remv|Purg)
        resolved=$package
        if [[ $package != *:* ]]; then
          # APT sometimes omits architecture. Resolve only when the installed
          # inventory has exactly one matching identity; never guess multiarch.
          matches=0
          for known in "${!known_packages[@]}"; do
            if [[ ${known%:*} == "$package" ]]; then
              resolved=$known
              matches=$((matches + 1))
            fi
          done
          if ((matches != 1)); then
            fail "Cannot uniquely identify APT removal $package. No changes made."; return 1
          fi
        fi
        approved=false
        for target in "${packages_to_remove[@]}"; do
          if [[ $resolved == "$target" ]]; then
            approved=true
            planned["$target"]=1
          fi
        done
        if [[ $approved != true ]]; then
          fail "APT would also remove $package. Refusing unselected removals."; return 1
        fi
        ;;
      Inst|Conf)
        fail 'APT would install or configure other packages. Resolve this separately.'; return 1
        ;;
    esac
  done <<<"$plan"
  for target in "${packages_to_remove[@]}"; do
    found=${planned[$target]-}
    [[ -n $found ]] || { fail "APT did not confirm removal of $target. No changes made."; return 1; }
  done
}

main() {
  local dry_run=false index confirm
  local current_kernel
  local -a candidates=() packages_to_remove=()
  local -A installed=() known_packages=()
  case ${1-} in
    --dry-run) dry_run=true; shift ;;
    -h|--help) usage; return 0 ;;
  esac
  (($# == 0)) || { usage >&2; return 1; }
  [[ $dry_run == true ]] || require_root || return
  collect_packages || return
  printf 'Currently running kernel: %s\n' "$current_kernel"
  if ((${#candidates[@]} == 0)); then
    printf '%s\n' 'No removable versioned kernels detected.'
    return 0
  fi
  printf '%s\n' 'Other installed kernel images (keep a known-good fallback):'
  for index in "${!candidates[@]}"; do
    printf '%2d. %s\n' "$((index + 1))" "${candidates[index]}"
  done
  select_packages || return
  if ((${#packages_to_remove[@]} == 0)); then
    printf '%s\n' 'No packages selected. Exiting.'
    return 0
  fi
  printf '\nSelected packages:\n'
  printf '  %s\n' "${packages_to_remove[@]}"
  simulate_removal || return
  if [[ $dry_run == true ]]; then
    printf '\nDry run complete. No packages or bootloader files were changed.\n'
    return 0
  fi
  printf '\nContinue to APT for final confirmation? (y/N): '
  if ! read -r confirm || [[ $confirm != y ]]; then
    printf '%s\n' 'Aborted.'
    return 0
  fi
  # One transaction, visible errors, and APT's own final prompt. Never use -y
  # or autoremove: unrelated packages and fallback kernels must stay put.
  if ! apt-get -o quiet=0 -o APT::Get::Assume-Yes=false -o APT::Get::force-yes=false \
      --no-auto-remove purge -- "${packages_to_remove[@]}"; then
    fail 'APT purge failed; cleanup stopped. Inspect the APT output above.'; return 1
  fi
  if command -v update-grub >/dev/null 2>&1; then
    update-grub || { fail 'Packages removed, but GRUB update failed.'; return 1; }
    printf '%s\n' 'Selected packages removed and GRUB updated.'
  else
    printf '%s\n' 'Selected packages removed. No update-grub command found; skipped.'
  fi
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
