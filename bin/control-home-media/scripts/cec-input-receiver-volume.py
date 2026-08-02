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
KEY_CHANNELUP = 402
KEY_CHANNELDOWN = 403

KEY_NAMES = {
    KEY_RED: "KEY_RED",
    KEY_GREEN: "KEY_GREEN",
    KEY_YELLOW: "KEY_YELLOW",
    KEY_BLUE: "KEY_BLUE",
    KEY_CHANNELUP: "KEY_CHANNELUP",
    KEY_CHANNELDOWN: "KEY_CHANNELDOWN",
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


def run_receiver_volume(control_media: str, config: str, receiver_id: str, delta: int, dry_run: bool) -> None:
    cmd = [
        control_media,
        "--config",
        config,
        "--type",
        "receiver",
        "--id",
        receiver_id,
        "set-volume",
        "--delta",
        str(delta),
    ]

    if dry_run:
        log("DRY RUN: " + " ".join(repr(part) for part in cmd))
        return

    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"command not found: {e.filename}. If receiver control needs PHP, set CONTROL_MEDIA_PHP=/path/to/php."
        ) from e

    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).strip()
        raise RuntimeError(out or f"receiver volume command failed with exit code {proc.returncode}")


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


def run_color_key_action(code: int, color_key_commands: dict[int, str], dry_run: bool) -> None:
    command = color_key_commands.get(code)
    if not command:
        return
    run_shell_command(command, dry_run)


def read_events(
    event_device: str,
    control_media: str,
    config: str,
    receiver_id: str,
    volume_step: int,
    include_repeats: bool,
    color_key_commands: dict[int, str],
    dry_run: bool,
) -> None:
    event_format = "llHHI"
    event_size = struct.calcsize(event_format)

    log(f"Listening for CEC input events on {event_device}")
    log("Mapped: KEY_CHANNELUP -> receiver volume up, KEY_CHANNELDOWN -> receiver volume down")
    mapped_color_keys = [
        KEY_NAMES[code] for code in (KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE) if color_key_commands.get(code)
    ]
    if mapped_color_keys:
        log("Mapped color keys: " + ", ".join(mapped_color_keys))
    else:
        log("Recorded for future use: KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE")

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

            key_name = KEY_NAMES.get(code)
            if key_name:
                log(f"{key_name} value={value}")

            if code == KEY_CHANNELUP:
                try:
                    run_receiver_volume(control_media, config, receiver_id, volume_step, dry_run)
                except RuntimeError as e:
                    log(f"Action failed: {e}")
            elif code == KEY_CHANNELDOWN:
                try:
                    run_receiver_volume(control_media, config, receiver_id, -volume_step, dry_run)
                except RuntimeError as e:
                    log(f"Action failed: {e}")
            elif code in COLOR_KEY_COMMAND_ENV:
                try:
                    run_color_key_action(code, color_key_commands, dry_run)
                except RuntimeError as e:
                    log(f"Action failed: {e}")


def handle_key_code(
    code: int,
    control_media: str,
    config: str,
    receiver_id: str,
    volume_step: int,
    color_key_commands: dict[int, str],
    dry_run: bool,
) -> None:
    key_name = KEY_NAMES.get(code, f"KEY_{code}")
    log(f"{key_name} value=1")
    if code == KEY_CHANNELUP:
        run_receiver_volume(control_media, config, receiver_id, volume_step, dry_run)
    elif code == KEY_CHANNELDOWN:
        run_receiver_volume(control_media, config, receiver_id, -volume_step, dry_run)
    elif code in COLOR_KEY_COMMAND_ENV:
        run_color_key_action(code, color_key_commands, dry_run)


def main(argv: list[str]) -> int:
    project_dir = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(
        description="Handle Linux CEC input events and map selected remote buttons to media actions."
    )
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
        "--control-media",
        default=os.environ.get("CONTROL_MEDIA", str(project_dir / "control_media.py")),
        help="Path to control_media.py.",
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("CONTROL_MEDIA_CONFIG", str(project_dir / "control_media.config.json")),
        help="Path to control_media config.",
    )
    parser.add_argument(
        "--receiver-id",
        default=os.environ.get("MEDIA_RECEIVER_ID", "192.168.1.112"),
        help="Receiver IP/id.",
    )
    parser.add_argument(
        "--volume-step",
        type=int,
        default=int(os.environ.get("MEDIA_RECEIVER_VOLUME_STEP", "1")),
        help="Receiver volume delta per key press.",
    )
    parser.add_argument(
        "--include-repeats",
        action="store_true",
        default=os.environ.get("MEDIA_CEC_INPUT_INCLUDE_REPEATS") == "1",
        help="Also handle key repeat events where value=2.",
    )
    parser.add_argument(
        "--red-command",
        default=os.environ.get("MEDIA_CEC_KEY_RED_COMMAND"),
        help="Command to run when KEY_RED is pressed, for example: 'xdotool key ctrl+1'.",
    )
    parser.add_argument(
        "--green-command",
        default=os.environ.get("MEDIA_CEC_KEY_GREEN_COMMAND"),
        help="Command to run when KEY_GREEN is pressed.",
    )
    parser.add_argument(
        "--yellow-command",
        default=os.environ.get("MEDIA_CEC_KEY_YELLOW_COMMAND"),
        help="Command to run when KEY_YELLOW is pressed.",
    )
    parser.add_argument(
        "--blue-command",
        default=os.environ.get("MEDIA_CEC_KEY_BLUE_COMMAND"),
        help="Command to run when KEY_BLUE is pressed.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print receiver commands without running them.")
    parser.add_argument(
        "--cec-refresh-command",
        default=os.environ.get("MEDIA_CEC_REFRESH_COMMAND"),
        help="Optional command to run before listening, e.g. the HDMI-CEC wakeup scenario.",
    )
    parser.add_argument(
        "--test-key-code",
        type=int,
        help="Handle one synthetic key code and exit. Useful for verifying mappings.",
    )
    args = parser.parse_args(argv)
    color_key_commands = {
        KEY_RED: args.red_command,
        KEY_GREEN: args.green_command,
        KEY_YELLOW: args.yellow_command,
        KEY_BLUE: args.blue_command,
    }

    if args.test_key_code is not None:
        handle_key_code(
            code=args.test_key_code,
            control_media=args.control_media,
            config=args.config,
            receiver_id=args.receiver_id,
            volume_step=args.volume_step,
            color_key_commands=color_key_commands,
            dry_run=args.dry_run,
        )
        return 0

    if args.cec_refresh_command:
        log(f"Refreshing CEC state: {args.cec_refresh_command}")
        run_cec_refresh(args.cec_refresh_command, args.dry_run)

    event_device = args.event_device or find_input_device(args.device_name_pattern)
    if not event_device:
        raise RuntimeError(
            "CEC input event device was not found. Set MEDIA_CEC_INPUT_DEVICE=/dev/input/eventN."
        )

    read_events(
        event_device=event_device,
        control_media=args.control_media,
        config=args.config,
        receiver_id=args.receiver_id,
        volume_step=args.volume_step,
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
