#!/usr/bin/env python3
# Version: 1
import argparse
import fcntl
import os
import socket
import struct
import sys
import time
from pathlib import Path


EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0

ABS_X = 0x00
ABS_Y = 0x01
ABS_Z = 0x02
ABS_RX = 0x03
ABS_RY = 0x04
ABS_RZ = 0x05
ABS_HAT0X = 0x10
ABS_HAT0Y = 0x11

BTN_SOUTH = 0x130  # A
BTN_EAST = 0x131  # B
BTN_NORTH = 0x133  # Top face button
BTN_WEST = 0x134  # Left face button
BTN_TL = 0x136
BTN_TR = 0x137
BTN_SELECT = 0x13A
BTN_START = 0x13B
BTN_MODE = 0x13C  # Guide/Home
BTN_THUMBL = 0x13D
BTN_THUMBR = 0x13E

BUS_USB = 0x03
DEFAULT_VENDOR = 0x045E
DEFAULT_PRODUCT = 0x028E
DEFAULT_VERSION = 0x0001

PROFILES = {
    "xbox360": {
        "name": "IR Remote Gamepad",
        "vendor": 0x045E,
        "product": 0x028E,
        "version": 0x0001,
        "button_map": {
            "x": BTN_WEST,
            "y": BTN_NORTH,
        },
    },
    "8bitdo-ultimate-2c": {
        "name": "8BitDo Ultimate 2C Wireless Controller",
        "vendor": 0x2DC8,
        "product": 0x310A,
        "version": 0x0114,
        "button_map": {
            "x": BTN_NORTH,
            "y": BTN_WEST,
        },
    },
}

UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405C5503
UI_ABS_SETUP = 0x401C5504
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567

BASE_BUTTON_CODES = {
    "a": BTN_SOUTH,
    "b": BTN_EAST,
    "x-north": BTN_NORTH,
    "y-west": BTN_WEST,
    "home": BTN_MODE,
    "guide": BTN_MODE,
    "steam": BTN_MODE,
    "select": BTN_SELECT,
    "start": BTN_START,
    "lb": BTN_TL,
    "rb": BTN_TR,
    "l3": BTN_THUMBL,
    "r3": BTN_THUMBR,
}

SUPPORTED_KEYS = (
    BTN_SOUTH,
    BTN_EAST,
    BTN_NORTH,
    BTN_WEST,
    BTN_TL,
    BTN_TR,
    BTN_SELECT,
    BTN_START,
    BTN_MODE,
    BTN_THUMBL,
    BTN_THUMBR,
)

SUPPORTED_ABS = (ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y)


def default_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return str(Path(runtime_dir) / "control-home-media" / "steam-gamepad.sock")
    return "/tmp/control-home-media-steam-gamepad.sock"


def emit(fd: int, event_type: int, code: int, value: int) -> None:
    os.write(fd, struct.pack("llHHI", 0, 0, event_type, code, value))


def sync(fd: int) -> None:
    emit(fd, EV_SYN, SYN_REPORT, 0)


def log(message: str, *, verbose: bool) -> None:
    if verbose:
        print(message, flush=True)


def ioctl_int(fd: int, request: int, value: int) -> None:
    fcntl.ioctl(fd, request, value)


def ioctl_checked(fd: int, request: int, arg: int | bytes, label: str) -> None:
    try:
        fcntl.ioctl(fd, request, arg)
    except OSError as e:
        raise OSError(e.errno, f"{label}: {e.strerror}") from e


def ioctl_int_checked(fd: int, request: int, value: int, label: str) -> None:
    try:
        ioctl_int(fd, request, value)
    except OSError as e:
        raise OSError(e.errno, f"{label}: {e.strerror}") from e


def create_virtual_gamepad(fd: int, name: str, vendor: int, product: int, version: int, *, verbose: bool) -> None:
    log("Enabling uinput event bits", verbose=verbose)
    ioctl_int_checked(fd, UI_SET_EVBIT, EV_KEY, "enable EV_KEY")
    ioctl_int_checked(fd, UI_SET_EVBIT, EV_ABS, "enable EV_ABS")

    for key_code in SUPPORTED_KEYS:
        ioctl_int_checked(fd, UI_SET_KEYBIT, key_code, f"enable key code {key_code}")

    for abs_code in SUPPORTED_ABS:
        ioctl_int_checked(fd, UI_SET_ABSBIT, abs_code, f"enable abs code {abs_code}")

    log(
        f"Setting up virtual gamepad: name={name!r}, vendor=0x{vendor:04x}, "
        f"product=0x{product:04x}, version=0x{version:04x}",
        verbose=verbose,
    )
    setup = struct.pack(
        "HHHH80sI",
        BUS_USB,
        vendor,
        product,
        version,
        name.encode("utf-8")[:79],
        0,
    )
    ioctl_checked(fd, UI_DEV_SETUP, setup, "setup uinput device")

    for abs_code in (ABS_X, ABS_Y, ABS_RX, ABS_RY):
        abs_setup = struct.pack("H2xiiiiii", abs_code, 0, -32768, 32767, 0, 128, 0)
        ioctl_checked(fd, UI_ABS_SETUP, abs_setup, f"setup abs code {abs_code}")

    for abs_code in (ABS_Z, ABS_RZ):
        abs_setup = struct.pack("H2xiiiiii", abs_code, 0, 0, 255, 0, 0, 0)
        ioctl_checked(fd, UI_ABS_SETUP, abs_setup, f"setup trigger code {abs_code}")

    for abs_code in (ABS_HAT0X, ABS_HAT0Y):
        abs_setup = struct.pack("H2xiiiiii", abs_code, 0, -1, 1, 0, 0, 0)
        ioctl_checked(fd, UI_ABS_SETUP, abs_setup, f"setup hat code {abs_code}")

    log("Creating uinput device", verbose=verbose)
    ioctl_checked(fd, UI_DEV_CREATE, 0, "create uinput device")


def button_codes_for_profile(profile: str) -> dict[str, int]:
    if profile not in PROFILES:
        raise ValueError("unsupported profile: " + profile + ". Supported: " + ", ".join(sorted(PROFILES)))
    codes = dict(BASE_BUTTON_CODES)
    codes.update(PROFILES[profile]["button_map"])
    return codes


def parse_shortcut(shortcut: str, *, profile: str) -> list[int]:
    button_codes = button_codes_for_profile(profile)
    names = [part.strip().lower() for part in shortcut.split("+") if part.strip()]
    if not names:
        raise ValueError("shortcut is empty")

    unknown = [name for name in names if name not in button_codes]
    if unknown:
        raise ValueError(
            "unsupported button(s): "
            + ", ".join(unknown)
            + ". Supported: "
            + ", ".join(sorted(button_codes))
        )

    return [button_codes[name] for name in names]


def emit_shortcut(
    fd: int,
    shortcut: str,
    button_codes: list[int],
    *,
    hold_seconds: float,
    chord_delay_seconds: float,
    verbose: bool,
) -> None:
    log(f"Pressing {shortcut}: {button_codes}", verbose=verbose)
    if len(button_codes) > 1 and button_codes[0] == BTN_MODE:
        emit(fd, EV_KEY, BTN_MODE, 1)
        sync(fd)
        log(f"Holding Home before chord for {chord_delay_seconds:.3f}s", verbose=verbose)
        time.sleep(chord_delay_seconds)

        for code in button_codes[1:]:
            emit(fd, EV_KEY, code, 1)
        sync(fd)

        time.sleep(hold_seconds)

        for code in reversed(button_codes[1:]):
            emit(fd, EV_KEY, code, 0)
        sync(fd)

        log(f"Holding Home after chord for {chord_delay_seconds:.3f}s", verbose=verbose)
        time.sleep(chord_delay_seconds)
        emit(fd, EV_KEY, BTN_MODE, 0)
        sync(fd)
        return

    for code in button_codes:
        emit(fd, EV_KEY, code, 1)
    sync(fd)

    time.sleep(hold_seconds)

    for code in reversed(button_codes):
        emit(fd, EV_KEY, code, 0)
    sync(fd)


def press_shortcut(
    shortcut: str,
    *,
    uinput_path: str,
    hold_seconds: float,
    chord_delay_seconds: float,
    settle_seconds: float,
    keepalive_seconds: float,
    device_name: str,
    vendor: int,
    product: int,
    version: int,
    profile: str,
    verbose: bool,
    dry_run: bool,
) -> None:
    button_codes = parse_shortcut(shortcut, profile=profile)

    if dry_run:
        print(
            f"DRY RUN: create virtual gamepad on {uinput_path}, "
            f"wait {settle_seconds:.3f}s, press {shortcut} for {hold_seconds:.3f}s, "
            f"chord delay {chord_delay_seconds:.3f}s, "
            f"keep alive {keepalive_seconds:.3f}s"
        )
        return

    log(f"Opening {uinput_path}", verbose=verbose)
    fd = os.open(uinput_path, os.O_WRONLY | os.O_NONBLOCK)
    created = False
    try:
        create_virtual_gamepad(fd, device_name, vendor, product, version, verbose=verbose)
        created = True
        log(f"Waiting {settle_seconds:.3f}s for Steam/input stack to notice the device", verbose=verbose)
        time.sleep(settle_seconds)

        emit_shortcut(
            fd,
            shortcut,
            button_codes,
            hold_seconds=hold_seconds,
            chord_delay_seconds=chord_delay_seconds,
            verbose=verbose,
        )

        log(f"Keeping virtual gamepad alive for {keepalive_seconds:.3f}s", verbose=verbose)
        time.sleep(keepalive_seconds)
    finally:
        if created:
            log("Destroying uinput device", verbose=verbose)
            fcntl.ioctl(fd, UI_DEV_DESTROY)
        os.close(fd)


def send_to_daemon(shortcut: str, socket_path: str, timeout_seconds: float) -> bool:
    if not os.path.exists(socket_path):
        return False

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout_seconds)
    try:
        client.connect(socket_path)
        client.sendall((shortcut + "\n").encode("utf-8"))
        response = client.recv(4096).decode("utf-8", errors="replace").strip()
    except OSError:
        return False
    finally:
        client.close()

    if response == "OK":
        return True
    if response:
        raise RuntimeError(response)
    raise RuntimeError("daemon returned an empty response")


def run_daemon(
    *,
    socket_path: str,
    uinput_path: str,
    hold_seconds: float,
    chord_delay_seconds: float,
    settle_seconds: float,
    device_name: str,
    vendor: int,
    product: int,
    version: int,
    profile: str,
    verbose: bool,
) -> None:
    log(f"Opening {uinput_path}", verbose=verbose)
    fd = os.open(uinput_path, os.O_WRONLY | os.O_NONBLOCK)
    created = False
    server: socket.socket | None = None
    try:
        create_virtual_gamepad(fd, device_name, vendor, product, version, verbose=verbose)
        created = True
        log(f"Waiting {settle_seconds:.3f}s for Steam/input stack to notice the device", verbose=verbose)
        time.sleep(settle_seconds)

        path = Path(socket_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(socket_path)
        os.chmod(socket_path, 0o600)
        server.listen(8)
        print(f"Listening on {socket_path}", flush=True)

        while True:
            conn, _addr = server.accept()
            with conn:
                request = conn.recv(4096).decode("utf-8", errors="replace").strip()
                try:
                    button_codes = parse_shortcut(request, profile=profile)
                    emit_shortcut(
                        fd,
                        request,
                        button_codes,
                        hold_seconds=hold_seconds,
                        chord_delay_seconds=chord_delay_seconds,
                        verbose=verbose,
                    )
                except Exception as e:
                    conn.sendall((f"ERROR: {e}\n").encode("utf-8"))
                else:
                    conn.sendall(b"OK\n")
    finally:
        if server is not None:
            server.close()
        try:
            if os.path.exists(socket_path):
                os.unlink(socket_path)
        except OSError:
            pass
        if created:
            log("Destroying uinput device", verbose=verbose)
            fcntl.ioctl(fd, UI_DEV_DESTROY)
        os.close(fd)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Send a short virtual gamepad shortcut via /dev/uinput.")
    parser.add_argument(
        "shortcut",
        nargs="?",
        help="Shortcut like home, home+a, home+x, shift alternatives are not supported here.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=os.environ.get("STEAM_GAMEPAD_SHORTCUT_PROFILE", "8bitdo-ultimate-2c"),
        help="Virtual gamepad profile. Default: 8bitdo-ultimate-2c.",
    )
    parser.add_argument(
        "--uinput",
        default=os.environ.get("UINPUT_DEVICE", "/dev/uinput"),
        help="uinput device path, default: /dev/uinput.",
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=float(os.environ.get("STEAM_GAMEPAD_SHORTCUT_HOLD_SECONDS", "0.20")),
        help="Button hold duration in seconds.",
    )
    parser.add_argument(
        "--chord-delay",
        type=float,
        default=float(os.environ.get("STEAM_GAMEPAD_SHORTCUT_CHORD_DELAY_SECONDS", "0.20")),
        help="Delay before and after non-Home buttons in Home chords.",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=float(os.environ.get("STEAM_GAMEPAD_SHORTCUT_SETTLE_SECONDS", "2.00")),
        help="Delay after creating the virtual gamepad before sending buttons.",
    )
    parser.add_argument(
        "--keepalive",
        type=float,
        default=float(os.environ.get("STEAM_GAMEPAD_SHORTCUT_KEEPALIVE_SECONDS", "2.00")),
        help="Delay after releasing buttons before destroying the virtual gamepad.",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("STEAM_GAMEPAD_SHORTCUT_DEVICE_NAME"),
        help="Virtual gamepad device name.",
    )
    parser.add_argument(
        "--vendor",
        type=lambda value: int(value, 0),
        default=os.environ.get("STEAM_GAMEPAD_SHORTCUT_VENDOR"),
        help="USB vendor id, default: 0x045e.",
    )
    parser.add_argument(
        "--product",
        type=lambda value: int(value, 0),
        default=os.environ.get("STEAM_GAMEPAD_SHORTCUT_PRODUCT"),
        help="USB product id, default: 0x028e.",
    )
    parser.add_argument(
        "--version",
        type=lambda value: int(value, 0),
        default=os.environ.get("STEAM_GAMEPAD_SHORTCUT_VERSION"),
        help="USB device version.",
    )
    parser.add_argument(
        "--socket",
        default=os.environ.get("STEAM_GAMEPAD_SHORTCUT_SOCKET", default_socket_path()),
        help="Unix socket path for daemon mode.",
    )
    parser.add_argument(
        "--daemon-timeout",
        type=float,
        default=float(os.environ.get("STEAM_GAMEPAD_SHORTCUT_DAEMON_TIMEOUT_SECONDS", "1.0")),
        help="Client timeout when sending shortcut to daemon.",
    )
    parser.add_argument("--daemon", action="store_true", help="Keep a virtual gamepad alive and listen on a socket.")
    parser.add_argument("--oneshot", action="store_true", help="Do not send to daemon; create a temporary device.")
    parser.add_argument("--verbose", action="store_true", help="Print setup and button emission steps.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without touching uinput.")
    args = parser.parse_args(argv)
    profile = PROFILES[args.profile]
    device_name = args.name or str(profile.get("name") or PROFILES["xbox360"]["name"])
    vendor = int(args.vendor, 0) if isinstance(args.vendor, str) else (args.vendor or int(profile["vendor"]))
    product = int(args.product, 0) if isinstance(args.product, str) else (args.product or int(profile["product"]))
    version = int(args.version, 0) if isinstance(args.version, str) else (args.version or int(profile["version"]))

    if args.daemon:
        if args.dry_run:
            print(
                f"DRY RUN: start daemon on {args.socket}, create virtual gamepad on {args.uinput}, "
                f"wait {args.settle:.3f}s"
            )
            return 0
        run_daemon(
            socket_path=args.socket,
            uinput_path=args.uinput,
            hold_seconds=args.hold,
            chord_delay_seconds=args.chord_delay,
            settle_seconds=args.settle,
            device_name=device_name,
            vendor=vendor,
            product=product,
            version=version,
            profile=args.profile,
            verbose=args.verbose,
        )
        return 0

    if not args.shortcut:
        parser.error("shortcut is required unless --daemon is used")

    if not args.dry_run and not args.oneshot and send_to_daemon(args.shortcut, args.socket, args.daemon_timeout):
        return 0

    press_shortcut(
        args.shortcut,
        uinput_path=args.uinput,
        hold_seconds=args.hold,
        chord_delay_seconds=args.chord_delay,
        settle_seconds=args.settle,
        keepalive_seconds=args.keepalive,
        device_name=device_name,
        vendor=vendor,
        product=product,
        version=version,
        profile=args.profile,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except PermissionError as e:
        print(f"Error: no permission for {e.filename}. Check /dev/uinput permissions.", file=sys.stderr)
        raise SystemExit(2)
    except FileNotFoundError as e:
        print(f"Error: not found: {e.filename}. Load uinput module or check device path.", file=sys.stderr)
        raise SystemExit(2)
    except (OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(2)
