#!/usr/bin/env bash
# Wallpapers photographed by Yuval Kolodkin-Gal (@yuvalkolodkingal).
# Keep the payload pinned; update this SHA when publishing a new installer.
set -euo pipefail
SOURCE_REF='97a73e0e951978f637b627f6ff086b29d1946d30'
TMP_DIR=''

usage() {
  cat <<'HELP'
Install Yuval Kolodkin-Gal's wallpapers and optional Hyprland themes.

Usage: bash install.sh [options]
  --theme NAME     all (default), canopy, lagoon, ember, or dusk
  --target TYPE    auto (default), omarchy, hyprland, or wallpapers
  --dest PATH      Override the installation parent directory
  --resolution SIZE  1920x1080 (default) or master; wallpapers target only
  --dry-run        Show the plan without writing to the destination
  --apply          Activate one theme on Omarchy after installation
  --help           Show this help

Auto selects Omarchy or Hyprland when detected on Linux, otherwise wallpapers.
macOS and other Unix systems receive wallpapers. No packages or sudo required;
you need curl, tar, and Python 3.11+. Installation preserves existing files and
does not change the running desktop unless you explicitly pass --apply.
HELP
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
cleanup() { if [[ -n "$TMP_DIR" ]]; then rm -rf -- "$TMP_DIR"; fi; }

main() {
  local theme=all target=auto destination='' resolution=1920x1080 apply=false dry_run=false option os
  while (($#)); do
    option=$1
    case "$option" in
      --theme|--target|--dest|--resolution)
        (($# >= 2)) && [[ -n "$2" && "$2" != --* ]] || fail "$option requires a value."
        case "$option" in
          --theme) theme=$2 ;; --target) target=$2 ;; --dest) destination=$2 ;;
          --resolution) resolution=$2 ;;
        esac
        shift 2 ;;
      --apply) apply=true; shift ;;
      --dry-run) dry_run=true; shift ;;
      --help|-h) usage; return ;;
      *) fail "Unknown option: $option (use --help)." ;;
    esac
  done
  case "$theme" in all|canopy|lagoon|ember|dusk) ;; *) fail "Unknown theme: $theme" ;; esac
  case "$target" in auto|omarchy|hyprland|wallpapers) ;; *) fail "Unknown target: $target" ;; esac
  case "$resolution" in 1920x1080|master) ;; *) fail "Unknown resolution: $resolution" ;; esac
  os=$(uname -s)
  if [[ "$target" == auto ]]; then
    target=wallpapers
    if [[ "$os" == Linux ]]; then
      if command -v omarchy >/dev/null 2>&1; then target=omarchy
      elif command -v Hyprland >/dev/null 2>&1 || command -v hyprctl >/dev/null 2>&1; then target=hyprland
      fi
    fi
  fi
  if [[ "$target" != wallpapers && "$os" != Linux ]]; then
    fail "$target requires Linux; use --target wallpapers on this system."
  fi
  [[ "$target" == wallpapers || "$resolution" == 1920x1080 ]] || fail '--resolution master requires --target wallpapers.'
  if $apply; then
    [[ "$target" == omarchy ]] || fail '--apply is only available with --target omarchy.'
    [[ "$theme" != all ]] || fail '--apply requires one named --theme.'
    [[ -z "$destination" ]] || fail '--apply cannot be combined with --dest.'
    if ! $dry_run; then
      command -v omarchy >/dev/null 2>&1 || fail 'Omarchy is required for --apply.'
      command -v hyprctl >/dev/null 2>&1 && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] ||
        fail 'Run --apply inside your active Hyprland session.'
    fi
  fi
  for option in curl tar python3; do
    command -v "$option" >/dev/null 2>&1 || fail "Missing dependency: $option"
  done
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail 'Python 3.11 or newer is required.'
  TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/yuval-wallpapers.XXXXXXXX")
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
  printf 'Downloading wallpapers (target: %s, theme: %s)…\n' "$target" "$theme"
  curl --fail --show-error --location --proto '=https' --proto-redir '=https' \
    --retry 2 --connect-timeout 15 --output "$TMP_DIR/source.tar.gz" \
    "https://codeload.github.com/yuvalkolodkingal/Wallpapers/tar.gz/$SOURCE_REF" || fail 'Download failed; nothing was installed.'
  # Validate before tar extracts: no escaping paths, devices, or directory links.
  python3 - "$TMP_DIR/source.tar.gz" "Wallpapers-$SOURCE_REF" <<'PY' || fail 'Invalid source archive; nothing was installed.'
import posixpath
import sys
import tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], 'r:gz') as archive:
    members = archive.getmembers()
    entries = {member.name.rstrip('/'): member for member in members}
    if len(entries) != len(members):
        raise ValueError('Duplicate archive entries')
    root = sys.argv[2]
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or path.parts[0] != root or str(path) != member.name.rstrip('/')):
            raise ValueError(f'Unsafe archive path: {member.name}')
        if not (member.isfile() or member.isdir() or member.issym()):
            raise ValueError(f'Unsupported archive entry: {member.name}')
        for parent in path.parents:
            if str(parent) in entries and not entries[str(parent)].isdir():
                raise ValueError(f'Non-directory ancestor: {member.name}')
        if member.issym():
            target = posixpath.normpath(posixpath.join(str(path.parent), member.linkname))
            if not target.startswith(root + '/') or target not in entries or not entries[target].isfile():
                raise ValueError(f'Unsafe archive link: {member.name}')
PY
  tar -xzf "$TMP_DIR/source.tar.gz" -C "$TMP_DIR" --no-same-owner --no-same-permissions || fail 'Could not unpack the source archive.'
  local payload="$TMP_DIR/Wallpapers-$SOURCE_REF/scripts/theme.py"
  [[ -f "$payload" ]] || fail 'Downloaded archive is missing scripts/theme.py.'
  local args=(install "$theme" --target "$target")
  [[ "$target" != wallpapers ]] || args+=(--resolution "$resolution")
  [[ -z "$destination" ]] || args+=(--dest "$destination")
  if $dry_run; then args+=(--dry-run); fi
  python3 "$payload" "${args[@]}"
  if $apply; then
    if $dry_run; then printf 'Would activate Omarchy theme: ykg-%s\n' "$theme"
    else python3 "$payload" apply "$theme"
    fi
  fi
}

# Nothing runs until Bash has received every function, including main, in full.
main "$@"
