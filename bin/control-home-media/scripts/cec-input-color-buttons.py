#!/usr/bin/env python3
# Version: 5
import argparse
import errno
import fcntl
import os
import re
import shlex
import struct
import subprocess
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path


EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0
KEY_MAX = 0x2FF
KEY_RED = 398
KEY_GREEN = 399
KEY_YELLOW = 400
KEY_BLUE = 401
KEY_1 = 2
KEY_2 = 3
KEY_4 = 5
KEY_5 = 6
KEY_NUMERIC_1 = 513
KEY_NUMERIC_2 = 514
KEY_NUMERIC_4 = 516
KEY_NUMERIC_5 = 517

KEY_NAMES = {
    KEY_RED: "KEY_RED",
    KEY_GREEN: "KEY_GREEN",
    KEY_YELLOW: "KEY_YELLOW",
    KEY_BLUE: "KEY_BLUE",
    KEY_1: "KEY_1",
    KEY_2: "KEY_2",
    KEY_4: "KEY_4",
    KEY_5: "KEY_5",
    KEY_NUMERIC_1: "KEY_NUMERIC_1",
    KEY_NUMERIC_2: "KEY_NUMERIC_2",
    KEY_NUMERIC_4: "KEY_NUMERIC_4",
    KEY_NUMERIC_5: "KEY_NUMERIC_5",
}

REMOTE_KEY_COMMAND_ENV = {
    KEY_RED: "MEDIA_CEC_KEY_RED_COMMAND",
    KEY_GREEN: "MEDIA_CEC_KEY_GREEN_COMMAND",
    KEY_YELLOW: "MEDIA_CEC_KEY_YELLOW_COMMAND",
    KEY_BLUE: "MEDIA_CEC_KEY_BLUE_COMMAND",
    KEY_1: "MEDIA_CEC_KEY_1_COMMAND",
    KEY_2: "MEDIA_CEC_KEY_2_COMMAND",
    KEY_4: "MEDIA_CEC_KEY_4_COMMAND",
    KEY_5: "MEDIA_CEC_KEY_5_COMMAND",
    KEY_NUMERIC_1: "MEDIA_CEC_KEY_1_COMMAND",
    KEY_NUMERIC_2: "MEDIA_CEC_KEY_2_COMMAND",
    KEY_NUMERIC_4: "MEDIA_CEC_KEY_4_COMMAND",
    KEY_NUMERIC_5: "MEDIA_CEC_KEY_5_COMMAND",
}

UNSAFE_CEC_COMMAND_TOKENS = {
    "--image-view-on",
    "image-view-on",
    "--active-source",
    "active-source",
}

UNAVAILABLE_PHYSICAL_ADDRESSES = {"f.f.f.f", "ffff", "65535"}
BUS_USB = 0x03
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405C5503
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
EVIOCGRAB = 0x40044590


@dataclass(frozen=True)
class CecStatus:
    state: str
    physical_address: str | None
    tv_present: bool
    power_status: str | None
    logical_address_present: bool
    reason: str


class RecoverableCecInputError(RuntimeError):
    pass


class VirtualKeyboard:
    def __init__(self, name: str = "Control Home Media CEC Keyboard") -> None:
        self.name = name
        self.fd: int | None = None

    def __enter__(self) -> "VirtualKeyboard":
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        for code in range(1, KEY_MAX + 1):
            try:
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
            except OSError:
                pass

        setup = struct.pack(
            "HHHH80sI",
            BUS_USB,
            0x1209,
            0xCECC,
            0x0001,
            self.name.encode("utf-8")[:79],
            0,
        )
        fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
        fcntl.ioctl(self.fd, UI_DEV_CREATE, 0)
        time.sleep(0.2)
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if self.fd is None:
            return

        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY, 0)
        finally:
            os.close(self.fd)
            self.fd = None

    def forward(self, event_type: int, code: int, value: int) -> None:
        if self.fd is None:
            return
        os.write(self.fd, struct.pack("llHHI", 0, 0, event_type, code, value))


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


def normalize_physical_address(raw: str | None) -> str | None:
    if raw is None:
        return None

    value = raw.strip().lower()
    if not value:
        return None
    if value == "65535":
        return "f.f.f.f"
    return value


def parse_cec_status(output: str) -> CecStatus:
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
        return CecStatus(
            state="cec_unavailable",
            physical_address=physical_address,
            tv_present=tv_present,
            power_status=power_status,
            logical_address_present=logical_address_present,
            reason="CEC physical address is unavailable",
        )

    if not logical_address_present:
        return CecStatus(
            state="cec_unavailable",
            physical_address=physical_address,
            tv_present=tv_present,
            power_status=power_status,
            logical_address_present=False,
            reason="CEC logical address is unavailable",
        )

    if not tv_present:
        return CecStatus(
            state="tv_not_on",
            physical_address=physical_address,
            tv_present=False,
            power_status=power_status,
            logical_address_present=logical_address_present,
            reason="TV is not present in CEC system information",
        )

    if power_status not in (None, "On", "Unknown"):
        return CecStatus(
            state="tv_not_on",
            physical_address=physical_address,
            tv_present=True,
            power_status=power_status,
            logical_address_present=logical_address_present,
            reason=f"TV power status is {power_status}",
        )

    return CecStatus(
        state="ready",
        physical_address=physical_address,
        tv_present=True,
        power_status=power_status,
        logical_address_present=logical_address_present,
        reason="CEC is ready",
    )


def command_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def is_unsafe_cec_listener_command(command: str) -> bool:
    tokens = command_tokens(command)
    lowered = [token.lower() for token in tokens]

    if any(token in UNSAFE_CEC_COMMAND_TOKENS for token in lowered):
        return True

    for token in lowered:
        if token == "10:04" or re.match(r"^[0-9a-f]{2}:04(?::|$)", token):
            return True
        if token == "10:82" or re.match(r"^[0-9a-f]{2}:82(?::|$)", token):
            return True

    for index, token in enumerate(lowered[:-1]):
        if token == "on" and lowered[index + 1] == "0":
            return True

    return False


def run_cec_command(command: str, dry_run: bool, label: str) -> None:
    cmd = shlex.split(command)
    if not cmd:
        return

    if dry_run:
        log(f"DRY RUN {label}: " + " ".join(repr(part) for part in cmd))
        return

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).strip()
        raise RuntimeError(out or f"{label} failed with exit code {proc.returncode}")


def run_cec_status_command(command: str | None, dry_run: bool) -> CecStatus:
    if not command:
        return CecStatus(
            state="ready",
            physical_address=None,
            tv_present=True,
            power_status=None,
            logical_address_present=True,
            reason="CEC status command is not configured",
        )

    cmd = shlex.split(command)
    if dry_run:
        log("DRY RUN CEC STATUS: " + " ".join(repr(part) for part in cmd))
        return CecStatus(
            state="ready",
            physical_address="dry-run",
            tv_present=True,
            power_status="On",
            logical_address_present=True,
            reason="Dry run",
        )

    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    except FileNotFoundError as e:
        return CecStatus(
            state="cec_unavailable",
            physical_address=None,
            tv_present=False,
            power_status=None,
            logical_address_present=False,
            reason=f"CEC status command not found: {e.filename}",
        )

    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        return CecStatus(
            state="cec_unavailable",
            physical_address=None,
            tv_present=False,
            power_status=None,
            logical_address_present=False,
            reason=(output.strip() or f"CEC status command failed with exit code {proc.returncode}"),
        )

    return parse_cec_status(output)


def wait_for_cec_ready(status_command: str | None, check_interval: float, dry_run: bool) -> CecStatus:
    last_state_key: tuple[str, str | None, str | None] | None = None

    while True:
        status = run_cec_status_command(status_command, dry_run)
        state_key = (status.state, status.physical_address, status.power_status)

        if status.state == "ready":
            log(f"CEC ready: physical_address={status.physical_address}, power_status={status.power_status}")
            return status

        if state_key != last_state_key:
            log(
                "CEC unavailable: "
                f"state={status.state}, reason={status.reason}, "
                f"physical_address={status.physical_address}, power_status={status.power_status}"
            )
            last_state_key = state_key

        time.sleep(check_interval)


def wait_for_input_device(event_device: str | None, name_pattern: str, check_interval: float) -> str:
    last_log = 0.0

    while True:
        found_device = event_device or find_input_device(name_pattern)
        if found_device:
            return found_device

        now = time.monotonic()
        if now - last_log >= 30:
            log("CEC input event device was not found. Waiting for it to appear.")
            last_log = now

        time.sleep(check_interval)


def select_safe_init_command(safe_init_command: str | None, legacy_refresh_command: str | None) -> str | None:
    if safe_init_command:
        return safe_init_command

    if not legacy_refresh_command:
        return None

    if is_unsafe_cec_listener_command(legacy_refresh_command):
        log("Ignoring unsafe deprecated MEDIA_CEC_REFRESH_COMMAND in listener.")
        return None

    log("Using deprecated MEDIA_CEC_REFRESH_COMMAND as safe listener init command.")
    return legacy_refresh_command


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


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in ("0", "false", "no", "off")


def grab_input_device(event_file: object, enabled: bool, dry_run: bool) -> bool:
    if not enabled or dry_run:
        return False

    fcntl.ioctl(event_file.fileno(), EVIOCGRAB, 1)
    return True


def release_input_device(event_file: object, grabbed: bool) -> None:
    if not grabbed:
        return

    try:
        fcntl.ioctl(event_file.fileno(), EVIOCGRAB, 0)
    except OSError:
        pass


def handle_key_code(code: int, key_commands: dict[int, str], dry_run: bool) -> None:
    key_name = KEY_NAMES.get(code)
    if not key_name:
        return

    log(f"{key_name} value=1")
    command = key_commands.get(code)
    if command:
        run_shell_command(command, dry_run)


def read_events(
    event_device: str,
    include_repeats: bool,
    key_commands: dict[int, str],
    grab_input: bool,
    dry_run: bool,
) -> None:
    event_format = "llHHI"
    event_size = struct.calcsize(event_format)

    log(f"Listening for CEC remote button events on {event_device}")
    mapped_keys = [
        KEY_NAMES[code]
        for code in (
            KEY_RED,
            KEY_GREEN,
            KEY_YELLOW,
            KEY_BLUE,
            KEY_1,
            KEY_2,
            KEY_4,
            KEY_5,
            KEY_NUMERIC_1,
            KEY_NUMERIC_2,
            KEY_NUMERIC_4,
            KEY_NUMERIC_5,
        )
        if key_commands.get(code)
    ]
    if mapped_keys:
        log("Mapped remote keys: " + ", ".join(mapped_keys))
    else:
        log("No remote key commands configured.")

    try:
        event_file = open(event_device, "rb", buffering=0)
    except OSError as e:
        if e.errno in (errno.ENODEV, errno.ENOENT, errno.EIO):
            raise RecoverableCecInputError(f"input device unavailable: {event_device}: {e}") from e
        raise

    virtual_keyboard_context = VirtualKeyboard() if grab_input and not dry_run else None
    context = virtual_keyboard_context or nullcontext()

    with event_file as f, context as virtual_keyboard:
        grabbed = grab_input_device(f, grab_input, dry_run)
        if grabbed:
            log("CEC input device grabbed; mapped keys will be suppressed and other keys forwarded.")

        try:
            while True:
                try:
                    data = f.read(event_size)
                except OSError as e:
                    if e.errno in (errno.ENODEV, errno.ENOENT, errno.EIO):
                        raise RecoverableCecInputError(f"input device disconnected: {event_device}: {e}") from e
                    raise

                if len(data) < event_size:
                    raise RecoverableCecInputError(f"short read from {event_device}")

                _sec, _usec, event_type, code, value = struct.unpack(event_format, data)
                command = key_commands.get(code)
                suppress_event = event_type == EV_KEY and bool(command)

                if not suppress_event and virtual_keyboard and event_type in (EV_KEY, EV_SYN):
                    virtual_keyboard.forward(event_type, code, value)

                if event_type != EV_KEY:
                    continue
                if value == 0:
                    continue
                if value == 2 and not include_repeats:
                    continue
                if not command:
                    continue

                try:
                    handle_key_code(code, key_commands, dry_run)
                except RuntimeError as e:
                    log(f"Action failed: {e}")
        finally:
            release_input_device(f, grabbed)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Handle Linux CEC remote button events.")
    parser.add_argument(
        "--event-device",
        default=os.environ.get("MEDIA_CEC_INPUT_DEVICE"),
        help="Input event device, for example /dev/input/event21. Defaults to auto-detecting CEC input devices.",
    )
    parser.add_argument(
        "--device-name-pattern",
        default=os.environ.get("MEDIA_CEC_INPUT_NAME_PATTERN", r"^(DP-4|cecd)"),
        help="Regex used for auto-detecting the CEC input device from /proc/bus/input/devices.",
    )
    parser.add_argument(
        "--include-repeats",
        action="store_true",
        default=os.environ.get("MEDIA_CEC_INPUT_INCLUDE_REPEATS") == "1",
        help="Also handle key repeat events where value=2.",
    )
    parser.add_argument(
        "--grab-input",
        action=argparse.BooleanOptionalAction,
        default=parse_bool(os.environ.get("MEDIA_CEC_INPUT_GRAB"), True),
        help="Grab the CEC input device, suppress mapped keys, and forward unmapped keys through uinput.",
    )
    parser.add_argument("--red-command", default=os.environ.get("MEDIA_CEC_KEY_RED_COMMAND"))
    parser.add_argument("--green-command", default=os.environ.get("MEDIA_CEC_KEY_GREEN_COMMAND"))
    parser.add_argument("--yellow-command", default=os.environ.get("MEDIA_CEC_KEY_YELLOW_COMMAND"))
    parser.add_argument("--blue-command", default=os.environ.get("MEDIA_CEC_KEY_BLUE_COMMAND"))
    parser.add_argument("--key-1-command", default=os.environ.get("MEDIA_CEC_KEY_1_COMMAND"))
    parser.add_argument("--key-2-command", default=os.environ.get("MEDIA_CEC_KEY_2_COMMAND"))
    parser.add_argument("--key-4-command", default=os.environ.get("MEDIA_CEC_KEY_4_COMMAND"))
    parser.add_argument("--key-5-command", default=os.environ.get("MEDIA_CEC_KEY_5_COMMAND"))
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--cec-refresh-command",
        default=os.environ.get("MEDIA_CEC_REFRESH_COMMAND"),
        help="Deprecated optional command to run before listening. Unsafe wake/source commands are ignored.",
    )
    parser.add_argument(
        "--cec-safe-init-command",
        default=os.environ.get("MEDIA_CEC_SAFE_INIT_COMMAND"),
        help="Optional safe command to run before listening, for example 'cec-ctl -d /dev/cec0 --playback -S'.",
    )
    parser.add_argument(
        "--cec-status-command",
        default=os.environ.get("MEDIA_CEC_STATUS_COMMAND"),
        help="Optional command used to detect CEC/TV power state before opening the input device.",
    )
    parser.add_argument(
        "--cec-check-interval",
        type=float,
        default=float(os.environ.get("MEDIA_CEC_CHECK_INTERVAL_SECONDS", "5")),
        help="Seconds between CEC/input recovery checks.",
    )
    parser.add_argument("--test-key-code", type=int, help="Handle one synthetic key code and exit.")
    args = parser.parse_args(argv)

    key_commands = {
        KEY_RED: args.red_command,
        KEY_GREEN: args.green_command,
        KEY_YELLOW: args.yellow_command,
        KEY_BLUE: args.blue_command,
        KEY_1: args.key_1_command,
        KEY_2: args.key_2_command,
        KEY_4: args.key_4_command,
        KEY_5: args.key_5_command,
        KEY_NUMERIC_1: args.key_1_command,
        KEY_NUMERIC_2: args.key_2_command,
        KEY_NUMERIC_4: args.key_4_command,
        KEY_NUMERIC_5: args.key_5_command,
    }

    if args.test_key_code is not None:
        handle_key_code(args.test_key_code, key_commands, args.dry_run)
        return 0

    init_command = select_safe_init_command(args.cec_safe_init_command, args.cec_refresh_command)
    if init_command:
        log(f"Initializing CEC listener state: {init_command}")
        run_cec_command(init_command, args.dry_run, "CEC INIT")

    while True:
        wait_for_cec_ready(args.cec_status_command, args.cec_check_interval, args.dry_run)
        event_device = wait_for_input_device(args.event_device, args.device_name_pattern, args.cec_check_interval)

        try:
            read_events(
                event_device=event_device,
                include_repeats=args.include_repeats,
                key_commands=key_commands,
                grab_input=args.grab_input,
                dry_run=args.dry_run,
            )
        except RecoverableCecInputError as e:
            log(f"CEC input recovering: {e}")
            time.sleep(args.cec_check_interval)

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
