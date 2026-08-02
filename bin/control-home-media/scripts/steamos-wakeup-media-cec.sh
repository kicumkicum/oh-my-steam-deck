#!/usr/bin/env bash
# Version: 1
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

CONTROL_MEDIA="${CONTROL_MEDIA:-$PROJECT_DIR/control_media.py}"
CONTROL_MEDIA_CONFIG="${CONTROL_MEDIA_CONFIG:-$PROJECT_DIR/control_media.config.json}"

MEDIA_STARTUP_DELAY_SECONDS="${MEDIA_STARTUP_DELAY_SECONDS:-5}"
MEDIA_STEP_DELAY_SECONDS="${MEDIA_STEP_DELAY_SECONDS:-1}"
MEDIA_RETRIES="${MEDIA_RETRIES:-5}"
MEDIA_RETRY_DELAY_SECONDS="${MEDIA_RETRY_DELAY_SECONDS:-2}"

MEDIA_CEC_RUNNER="${MEDIA_CEC_RUNNER:-}"
MEDIA_CEC_BACKEND="${MEDIA_CEC_BACKEND:-auto}"
MEDIA_CEC_CTL="${MEDIA_CEC_CTL:-cec-ctl}"
MEDIA_CEC_CLIENT="${MEDIA_CEC_CLIENT:-cec-client}"
MEDIA_CEC_DEVICE="${MEDIA_CEC_DEVICE:-}"
MEDIA_CEC_PHYS_ADDR="${MEDIA_CEC_PHYS_ADDR:-1.0.0.0}"
MEDIA_CEC_POWER_ON_TV="${MEDIA_CEC_POWER_ON_TV:-1}"
MEDIA_RECEIVER_ID="${MEDIA_RECEIVER_ID:-192.168.1.112}"
MEDIA_RECEIVER_SOURCE="${MEDIA_RECEIVER_SOURCE:-tv}"

DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage: steamos-wakeup-media-cec.sh [--dry-run]

This scenario is intended for SteamOS autostart on the mini-PC connected to TV
over HDMI. It asks HDMI-CEC to make this mini-PC the active HDMI source, then
switches the Harman Kardon receiver to source "tv".

Environment overrides:
  CONTROL_MEDIA                 Path to control_media.py
  CONTROL_MEDIA_CONFIG          Path to control_media.config.json
  MEDIA_STARTUP_DELAY_SECONDS   Delay before first command, default: 5
  MEDIA_STEP_DELAY_SECONDS      Delay between device commands, default: 1
  MEDIA_RETRIES                 Attempts per command, default: 5
  MEDIA_RETRY_DELAY_SECONDS     Delay between attempts, default: 2
  MEDIA_CEC_RUNNER              Optional command prefix, e.g. "distrobox enter media-cec --"
  MEDIA_CEC_BACKEND             auto|cec-ctl|cec-client, default: auto
  MEDIA_CEC_CTL                 cec-ctl binary for Linux /dev/cecX, default: cec-ctl
  MEDIA_CEC_CLIENT              cec-client binary for libCEC adapters, default: cec-client
  MEDIA_CEC_DEVICE              Optional CEC device path, auto-detects /dev/cec0
  MEDIA_CEC_PHYS_ADDR           HDMI physical address for active-source, default: 1.0.0.0
  MEDIA_CEC_POWER_ON_TV         Send CEC "on 0" before "as", default: 1
  MEDIA_RECEIVER_ID             Receiver IP/id, default: 192.168.1.112
  MEDIA_RECEIVER_SOURCE         Receiver source from config, default: tv
USAGE
}

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

cec_command() {
  if [[ -n "$MEDIA_CEC_RUNNER" ]]; then
    # MEDIA_CEC_RUNNER is intentionally shell-like so callers can pass:
    # "distrobox enter media-cec --"
    read -r -a runner_args <<< "$MEDIA_CEC_RUNNER"
    "${runner_args[@]}" "$@"
  else
    "$@"
  fi
}

print_cec_command() {
  if [[ -n "$MEDIA_CEC_RUNNER" ]]; then
    read -r -a runner_args <<< "$MEDIA_CEC_RUNNER"
    printf ' %q' "${runner_args[@]}"
  fi
  printf ' %q' "$@"
}

run_with_retries() {
  local label="$1"
  shift

  local attempt=1
  while (( attempt <= MEDIA_RETRIES )); do
    log "$label: attempt $attempt/$MEDIA_RETRIES"

    if (( DRY_RUN )); then
      if [[ "${1:-}" == "cec_active_source" ]]; then
        "$@"
        return 0
      fi
      printf 'DRY RUN:'
      printf ' %q' "$@"
      printf '\n'
      return 0
    fi

    if "$@"; then
      log "$label: ok"
      return 0
    fi

    if (( attempt == MEDIA_RETRIES )); then
      log "$label: failed"
      return 1
    fi

    sleep "$MEDIA_RETRY_DELAY_SECONDS"
    attempt=$((attempt + 1))
  done
}

cec_active_source() {
  case "$MEDIA_CEC_BACKEND" in
    cec-ctl)
      cec_active_source_with_cec_ctl
      ;;
    cec-client)
      cec_active_source_with_cec_client
      ;;
    *)
      log "Unsupported MEDIA_CEC_BACKEND: $MEDIA_CEC_BACKEND"
      return 2
      ;;
  esac
}

cec_active_source_with_cec_ctl() {
  local phys_addr="$MEDIA_CEC_PHYS_ADDR"

  if [[ "$phys_addr" == "auto" ]]; then
    if (( DRY_RUN )); then
      phys_addr="1.0.0.0"
    else
      phys_addr="$(cec_command "$MEDIA_CEC_CTL" -d "$MEDIA_CEC_DEVICE" --playback -s -x | awk 'NF { print $NF; exit }')"
    fi
  fi

  if [[ -z "$phys_addr" || "$phys_addr" == "f.f.f.f" ]]; then
    log "Unable to determine HDMI CEC physical address for $MEDIA_CEC_DEVICE."
    log "Run: $MEDIA_CEC_CTL -d $MEDIA_CEC_DEVICE --playback -S"
    log "Then set MEDIA_CEC_PHYS_ADDR to the reported physical address."
    return 2
  fi

  if (( DRY_RUN )); then
    printf 'DRY RUN:'
    print_cec_command "$MEDIA_CEC_CTL" -d "$MEDIA_CEC_DEVICE" --playback
    if [[ "$MEDIA_CEC_POWER_ON_TV" == "1" ]]; then
      printf ' %q' --to 0 --image-view-on
    fi
    printf ' %q' --to 0 --active-source "phys-addr=$phys_addr"
    printf '\n'
    return 0
  fi

  if [[ "$MEDIA_CEC_POWER_ON_TV" == "1" ]]; then
    cec_command "$MEDIA_CEC_CTL" -d "$MEDIA_CEC_DEVICE" --playback --to 0 --image-view-on --to 0 --active-source "phys-addr=$phys_addr"
  else
    cec_command "$MEDIA_CEC_CTL" -d "$MEDIA_CEC_DEVICE" --playback --to 0 --active-source "phys-addr=$phys_addr"
  fi
}

cec_active_source_with_cec_client() {
  local cec_args=(-s -d 1)
  local cec_commands

  if [[ -n "$MEDIA_CEC_DEVICE" ]]; then
    cec_args+=("$MEDIA_CEC_DEVICE")
  fi

  if [[ "$MEDIA_CEC_POWER_ON_TV" == "1" ]]; then
    cec_commands='on 0
as'
  else
    cec_commands='as'
  fi

  if (( DRY_RUN )); then
    printf 'DRY RUN: printf %q' "$cec_commands"
    printf ' |'
    print_cec_command "$MEDIA_CEC_CLIENT" "${cec_args[@]}"
    printf '\n'
    return 0
  fi

  printf '%s\n' "$cec_commands" | cec_command "$MEDIA_CEC_CLIENT" "${cec_args[@]}"
}

while (($#)); do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$MEDIA_CEC_DEVICE" ]] && [[ -e /dev/cec0 ]]; then
  MEDIA_CEC_DEVICE=/dev/cec0
fi

if (( DRY_RUN )) && [[ -z "$MEDIA_CEC_DEVICE" ]]; then
  MEDIA_CEC_DEVICE=/dev/cec0
fi

if [[ "$MEDIA_CEC_BACKEND" == "auto" ]]; then
  if [[ -n "$MEDIA_CEC_DEVICE" ]]; then
    MEDIA_CEC_BACKEND=cec-ctl
  else
    MEDIA_CEC_BACKEND=cec-client
  fi
fi

case "$MEDIA_CEC_BACKEND" in
  cec-ctl)
    if (( ! DRY_RUN )) && [[ -z "$MEDIA_CEC_RUNNER" ]] && ! command -v "$MEDIA_CEC_CTL" >/dev/null 2>&1; then
      log "cec-ctl is not found. Install v4l-utils on the mini-PC."
      exit 2
    fi
    if [[ -z "$MEDIA_CEC_DEVICE" ]]; then
      log "CEC device was not configured and /dev/cec0 was not found."
      log "Set MEDIA_CEC_DEVICE=/dev/cec0 or check: $MEDIA_CEC_CTL --list-devices"
      exit 2
    fi
    if (( ! DRY_RUN )) && [[ ! -r "$MEDIA_CEC_DEVICE" ]]; then
      log "CEC device is not readable by current user: $MEDIA_CEC_DEVICE"
      log "Check group access, for example: id && ls -al $MEDIA_CEC_DEVICE"
      exit 2
    fi
    ;;
  cec-client)
    if (( ! DRY_RUN )) && [[ -z "$MEDIA_CEC_RUNNER" ]] && ! command -v "$MEDIA_CEC_CLIENT" >/dev/null 2>&1; then
      log "cec-client is not found. Install libcec tools on the mini-PC."
      exit 2
    fi
    ;;
  *)
    log "Unsupported MEDIA_CEC_BACKEND: $MEDIA_CEC_BACKEND"
    exit 2
    ;;
esac

if [[ ! -x "$CONTROL_MEDIA" ]]; then
  log "control script is not executable or not found: $CONTROL_MEDIA"
  exit 2
fi

log "waiting ${MEDIA_STARTUP_DELAY_SECONDS}s before media wakeup scenario"
sleep "$MEDIA_STARTUP_DELAY_SECONDS"

run_with_retries "tv hdmi-cec active source" cec_active_source

sleep "$MEDIA_STEP_DELAY_SECONDS"

run_with_retries \
  "receiver source $MEDIA_RECEIVER_SOURCE" \
  "$CONTROL_MEDIA" \
  --config "$CONTROL_MEDIA_CONFIG" \
  --type receiver \
  --id "$MEDIA_RECEIVER_ID" \
  set-source \
  --source "$MEDIA_RECEIVER_SOURCE"

log "media wakeup scenario complete"
