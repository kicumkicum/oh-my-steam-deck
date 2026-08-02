#!/usr/bin/env python3
# Version: 1
import argparse
import os
import re
import shlex
import struct
import subprocess
import sys
from pathlib import Path


EV_KEY = 0x01
KEY_RED = 398
KEY_GREEN = 399
KEY_YELLOW = 400
KEY_BLUE = 401

KEY_NAMES = {
    KEY_RED: "KEY_RED",
    KEY_GREEN: "KEY_GREEN",
    KEY_YELLOW: "KEY_YELLOW",
    KEY_BLUE: "KEY_BLUE",
}

COLOR_KEY_COMMAND_ENV = {
    KEY_RED: "MEDIA_CEC_KEY_RED_COMMAND",
    KEY_GREEN: "MEDIA_CEC_KEY_GREEN_COMMAND",
    KEY_YELLOW: "MEDIA_CEC_KEY_YELLOW_COMMAND",
    KEY_BLUE: "MEDIA_CEC_KEY_BLUE_COMMAND",
}


def log(message: str) -> None:
    print(message, flush=True)


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


def run_cec_refresh(command: str, dry_run: bool) -> None:
    cmd = shlex.split(command)
    if not cmd:
        return

    if dry_run:
        log("DRY RUN CEC REFRESH: " + " ".join(repr(part) for part in cmd))
        return

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).strip()
        raise RuntimeError(out or f"CEC refresh command failed with exit code {proc.returncode}")


def run_shell_command(command: str, dry_run: bool) -> None:
    cmd = shlex.split(command)
    if not cmd:
        return

    if dry_run:
        log("DRY RUN ACTION: " + " ".join(repr(part) for part in cmd))
        return

    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(f"command not found: {e.filename}") from e

    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).strip()
        raise RuntimeError(out or f"command failed with exit code {proc.returncode}")


def handle_key_code(code: int, color_key_commands: dict[int, str], dry_run: bool) -> None:
    key_name = KEY_NAMES.get(code)
    if not key_name:
        return

    log(f"{key_name} value=1")
    command = color_key_commands.get(code)
    if command:
        run_shell_command(command, dry_run)


def read_events(
    event_device: str,
    include_repeats: bool,
    color_key_commands: dict[int, str],
    dry_run: bool,
) -> None:
    event_format = "llHHI"
    event_size = struct.calcsize(event_format)

    log(f"Listening for CEC color button events on {event_device}")
    mapped_color_keys = [
        KEY_NAMES[code] for code in (KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE) if color_key_commands.get(code)
    ]
    if mapped_color_keys:
        log("Mapped color keys: " + ", ".join(mapped_color_keys))
    else:
        log("No color key commands configured.")

    with open(event_device, "rb", buffering=0) as f:
        while True:
            data = f.read(event_size)
            if len(data) < event_size:
                raise RuntimeError(f"short read from {event_device}")

            _sec, _usec, event_type, code, value = struct.unpack(event_format, data)
            if event_type != EV_KEY:
                continue
            if value == 0:
                continue
            if value == 2 and not include_repeats:
                continue

            try:
                handle_key_code(code, color_key_commands, dry_run)
            except RuntimeError as e:
                log(f"Action failed: {e}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Handle Linux CEC color button events.")
    parser.add_argument(
        "--event-device",
        default=os.environ.get("MEDIA_CEC_INPUT_DEVICE"),
        help="Input event device, for example /dev/input/event21. Defaults to auto-detecting 'cecd'.",
    )
    parser.add_argument(
        "--device-name-pattern",
        default=os.environ.get("MEDIA_CEC_INPUT_NAME_PATTERN", r"^cecd\b"),
        help="Regex used for auto-detecting the CEC input device from /proc/bus/input/devices.",
    )
    parser.add_argument(
        "--include-repeats",
        action="store_true",
        default=os.environ.get("MEDIA_CEC_INPUT_INCLUDE_REPEATS") == "1",
        help="Also handle key repeat events where value=2.",
    )
    parser.add_argument("--red-command", default=os.environ.get("MEDIA_CEC_KEY_RED_COMMAND"))
    parser.add_argument("--green-command", default=os.environ.get("MEDIA_CEC_KEY_GREEN_COMMAND"))
    parser.add_argument("--yellow-command", default=os.environ.get("MEDIA_CEC_KEY_YELLOW_COMMAND"))
    parser.add_argument("--blue-command", default=os.environ.get("MEDIA_CEC_KEY_BLUE_COMMAND"))
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--cec-refresh-command",
        default=os.environ.get("MEDIA_CEC_REFRESH_COMMAND"),
        help="Optional command to run before listening.",
    )
    parser.add_argument("--test-key-code", type=int, help="Handle one synthetic key code and exit.")
    args = parser.parse_args(argv)

    color_key_commands = {
        KEY_RED: args.red_command,
        KEY_GREEN: args.green_command,
        KEY_YELLOW: args.yellow_command,
        KEY_BLUE: args.blue_command,
    }

    if args.test_key_code is not None:
        handle_key_code(args.test_key_code, color_key_commands, args.dry_run)
        return 0

    if args.cec_refresh_command:
        log(f"Refreshing CEC state: {args.cec_refresh_command}")
        run_cec_refresh(args.cec_refresh_command, args.dry_run)

    event_device = args.event_device or find_input_device(args.device_name_pattern)
    if not event_device:
        raise RuntimeError("CEC input event device was not found. Set MEDIA_CEC_INPUT_DEVICE=/dev/input/eventN.")

    read_events(
        event_device=event_device,
        include_repeats=args.include_repeats,
        color_key_commands=color_key_commands,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(2)
