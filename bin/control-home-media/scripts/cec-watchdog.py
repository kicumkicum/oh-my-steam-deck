#!/usr/bin/env python3
# Version: 3
import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_INPUT_PATTERN = r"^cecd\b"
DEFAULT_CECD_UNIT = "cecd.service"
DEFAULT_LISTENER_UNIT = "control-home-media-cec-buttons.service"
UNAVAILABLE_PHYSICAL_ADDRESSES = {"f.f.f.f", "ffff", "65535"}


def log(message: str) -> None:
    print(message, flush=True)


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in ("0", "false", "no", "off")


def runtime_dir() -> Path:
    value = os.environ.get("XDG_RUNTIME_DIR")
    if value:
        return Path(value) / "control-home-media"
    return Path("/tmp/control-home-media")


def default_state_file() -> str:
    return str(runtime_dir() / "cec-watchdog-input-missing-since")


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def find_input_device(name_pattern: str) -> str | None:
    devices_path = Path("/proc/bus/input/devices")
    if not devices_path.exists():
        return None

    chunks = devices_path.read_text(encoding="utf-8", errors="replace").split("\n\n")
    for chunk in chunks:
        name_match = re.search(r'^N: Name="(.+)"$', chunk, re.MULTILINE)
        handlers_match = re.search(r"^H: Handlers=(.+)$", chunk, re.MULTILINE)
        if not name_match or not handlers_match:
            continue

        if not re.search(name_pattern, name_match.group(1), re.IGNORECASE):
            continue

        for handler in handlers_match.group(1).split():
            if handler.startswith("event"):
                return f"/dev/input/{handler}"

    return None


def systemctl_user_show(unit: str, prop: str) -> str | None:
    proc = run(["systemctl", "--user", "show", unit, "-p", prop, "--value"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def service_active(unit: str) -> bool:
    return systemctl_user_show(unit, "ActiveState") == "active"


def service_main_pid(unit: str) -> int | None:
    value = systemctl_user_show(unit, "MainPID")
    if not value or value == "0":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def fd_count(pid: int) -> int | None:
    fd_path = Path("/proc") / str(pid) / "fd"
    try:
        return sum(1 for _ in fd_path.iterdir())
    except OSError:
        return None


def normalize_physical_address(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value == "65535":
        return "f.f.f.f"
    return value or None


def cec_ready(status_command: str | None) -> tuple[bool, str]:
    if not status_command:
        return True, "status command is not configured"

    try:
        proc = run(shlex.split(status_command))
    except FileNotFoundError as e:
        return False, f"status command not found: {e.filename}"

    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        return False, (output.strip() or f"status command failed with exit code {proc.returncode}")

    physical_address = None
    power_status = None
    tv_present = False
    logical_address_present = False
    in_tv_block = False

    for line in output.splitlines():
        stripped = line.strip()
        if re.match(r"^Logical Address\s+:", stripped):
            logical_address_present = True

        top_physical_match = re.match(r"^Physical Address\s+:\s+(.+)$", stripped)
        if top_physical_match and not in_tv_block:
            physical_address = normalize_physical_address(top_physical_match.group(1))

        if re.match(r"^System Information for device 0 \(TV\)", stripped):
            tv_present = True
            in_tv_block = True
            continue

        if in_tv_block and re.match(r"^System Information for device \d+ ", stripped):
            in_tv_block = False

        if in_tv_block:
            power_match = re.match(r"^Power Status\s+:\s+(.+)$", stripped)
            if power_match:
                power_status = power_match.group(1).strip()

    if not physical_address or physical_address in UNAVAILABLE_PHYSICAL_ADDRESSES:
        return False, f"physical address unavailable: {physical_address}"
    if not logical_address_present:
        return False, "logical address unavailable"
    if not tv_present:
        return False, "TV is not present in CEC status"
    if power_status not in (None, "On", "Unknown"):
        return False, f"TV power status is {power_status}"

    return True, f"physical_address={physical_address}, power_status={power_status}"


def read_missing_since(state_file: Path) -> float | None:
    try:
        return float(state_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_missing_since(state_file: Path, timestamp: float) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(f"{timestamp:.3f}\n", encoding="utf-8")


def clear_missing_since(state_file: Path) -> None:
    try:
        state_file.unlink()
    except FileNotFoundError:
        pass


def restart_units(cecd_unit: str, listener_unit: str, reason: str, dry_run: bool) -> int:
    log(f"CEC watchdog recovery: {reason}")
    cmd = ["systemctl", "--user", "restart", cecd_unit, listener_unit]
    if dry_run:
        log("DRY RUN: " + " ".join(shlex.quote(part) for part in cmd))
        return 0

    proc = run(cmd)
    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).strip()
        print(out or f"systemctl restart failed with exit code {proc.returncode}", file=sys.stderr)
        return proc.returncode
    return 0


def check_once(args: argparse.Namespace) -> int:
    if not args.enabled:
        log("CEC watchdog disabled.")
        return 0

    if args.force:
        return restart_units(args.cecd_unit, args.listener_unit, args.reason, args.dry_run)

    state_file = Path(args.state_file)
    cecd_active = service_active(args.cecd_unit)
    listener_active = service_active(args.listener_unit)

    if not cecd_active:
        return restart_units(args.cecd_unit, args.listener_unit, f"{args.cecd_unit} is not active", args.dry_run)

    cecd_pid = service_main_pid(args.cecd_unit)
    current_fd_count = fd_count(cecd_pid) if cecd_pid else None
    if current_fd_count is not None and current_fd_count >= args.fd_threshold:
        return restart_units(
            args.cecd_unit,
            args.listener_unit,
            f"{args.cecd_unit} fd count is {current_fd_count}, threshold is {args.fd_threshold}",
            args.dry_run,
        )

    input_device = find_input_device(args.input_name_pattern)
    if input_device:
        clear_missing_since(state_file)
        if not listener_active:
            return restart_units(args.cecd_unit, args.listener_unit, f"{args.listener_unit} is not active", args.dry_run)
        log(
            "CEC watchdog ok: "
            f"input={input_device}, cecd_fd_count={current_fd_count}, listener_active={listener_active}"
        )
        return 0

    if args.device_event:
        ready, reason = cec_ready(args.cec_status_command)
        if ready:
            return restart_units(
                args.cecd_unit,
                args.listener_unit,
                f"input missing after CEC device event while CEC is ready ({reason})",
                args.dry_run,
            )
        log(f"CEC watchdog waiting: device event, input missing, CEC not ready: {reason}")
        return 0

    ready, reason = cec_ready(args.cec_status_command)
    if not ready:
        clear_missing_since(state_file)
        log(f"CEC watchdog waiting: input missing, CEC not ready: {reason}")
        return 0

    now = time.time()
    missing_since = read_missing_since(state_file)
    if missing_since is None:
        write_missing_since(state_file, now)
        log(f"CEC watchdog waiting: input missing while CEC ready ({reason}); grace timer started")
        return 0

    missing_for = now - missing_since
    if missing_for < args.input_missing_grace_seconds:
        log(
            "CEC watchdog waiting: "
            f"input missing for {missing_for:.0f}s, grace is {args.input_missing_grace_seconds}s"
        )
        return 0

    clear_missing_since(state_file)
    return restart_units(
        args.cecd_unit,
        args.listener_unit,
        f"input missing for {missing_for:.0f}s while CEC is ready ({reason})",
        args.dry_run,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Recover SteamOS cecd when CEC input devices stop appearing.")
    parser.add_argument(
        "--enabled",
        action=argparse.BooleanOptionalAction,
        default=parse_bool(os.environ.get("MEDIA_CEC_WATCHDOG_ENABLED"), True),
    )
    parser.add_argument(
        "--cec-status-command",
        default=os.environ.get("MEDIA_CEC_STATUS_COMMAND"),
        help="Command used to detect whether CEC and TV are ready.",
    )
    parser.add_argument(
        "--input-name-pattern",
        default=os.environ.get("MEDIA_CEC_INPUT_NAME_PATTERN", DEFAULT_INPUT_PATTERN),
        help="Regex used for detecting the CEC input device from /proc/bus/input/devices.",
    )
    parser.add_argument(
        "--fd-threshold",
        type=int,
        default=int(os.environ.get("MEDIA_CEC_WATCHDOG_FD_THRESHOLD", "900")),
        help="Restart cecd when its open fd count reaches this threshold.",
    )
    parser.add_argument(
        "--input-missing-grace-seconds",
        type=float,
        default=float(os.environ.get("MEDIA_CEC_WATCHDOG_INPUT_MISSING_GRACE_SECONDS", "120")),
        help="Restart cecd when CEC is ready but its input device has been missing this long.",
    )
    parser.add_argument(
        "--state-file",
        default=os.environ.get("MEDIA_CEC_WATCHDOG_STATE_FILE", default_state_file()),
        help="File used to track how long the CEC input device has been missing.",
    )
    parser.add_argument(
        "--cecd-unit",
        default=os.environ.get("MEDIA_CEC_WATCHDOG_CECD_UNIT", DEFAULT_CECD_UNIT),
    )
    parser.add_argument(
        "--listener-unit",
        default=os.environ.get("MEDIA_CEC_WATCHDOG_LISTENER_UNIT", DEFAULT_LISTENER_UNIT),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Restart cecd and the listener immediately. Used by the /dev/cec0 path trigger.",
    )
    parser.add_argument(
        "--device-event",
        action="store_true",
        help="Check state after a CEC device path event and recover only if input is still missing.",
    )
    parser.add_argument(
        "--reason",
        default="CEC device path changed",
        help="Recovery reason logged when --force is used.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print recovery command without running it.")
    args = parser.parse_args(argv)

    return check_once(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        raise SystemExit(130)
