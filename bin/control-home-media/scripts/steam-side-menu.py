#!/usr/bin/env python3
"""Open a SteamOS side menu and keep it visible over Flatpak applications."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import struct
import subprocess
import time
import urllib.request


CDP_LIST_URL = "http://127.0.0.1:8080/json/list"

INSTALL_WORKAROUND = r"""
(() => {
    if (window.__controlHomeMediaOpaqueMenuTimer)
        return true;

    function findSteamInstance() {
        for (const node of document.querySelectorAll("*")) {
            const fiberKey = Object.keys(node).find(key => key.startsWith("__reactFiber$"));
            let fiber = fiberKey && node[fiberKey];
            while (fiber) {
                let context = fiber.dependencies?.firstContext;
                while (context) {
                    const value = context.memoizedValue;
                    if (value?.MenuStore && value?.CompositionStateStore)
                        return value;
                    context = context.next;
                }
                fiber = fiber.return;
            }
        }
        return null;
    }

    const instance = findSteamInstance();
    if (!instance)
        throw new Error("Steam Gamepad UI instance not found");

    const composition = instance.CompositionStateStore;
    const token = {};
    let forcedOpaque = false;
    let openedAt = 0;

    window.__controlHomeMediaOpaqueMenuTimer = setInterval(() => {
        const menuOpen = instance.MenuStore.GetOpenSideMenu() !== 0;
        if (menuOpen) {
            if (!openedAt)
                openedAt = Date.now();
            // Let the BrowserView finish its opening layout before switching the
            // Steam window to opaque composition. Otherwise CEF can show a blank
            // surface instead of the menu.
            if (!forcedOpaque && Date.now() - openedAt >= 1200) {
                composition.AddMinimumCompositionStateRequest(3, token);
                forcedOpaque = true;
            }
        } else {
            openedAt = 0;
            if (forcedOpaque) {
                composition.RemoveMinimumCompositionStateRequest(3, token);
                forcedOpaque = false;
            }
        }
    }, 50);

    return true;
})()
"""


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("CDP WebSocket closed unexpectedly")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    mask = secrets.token_bytes(4)
    length = len(payload)
    if length < 126:
        header = bytes((0x81, 0x80 | length))
    elif length < 65536:
        header = bytes((0x81, 0xFE)) + struct.pack("!H", length)
    else:
        header = bytes((0x81, 0xFF)) + struct.pack("!Q", length)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    sock.sendall(header + mask + masked)


def _recv_text(sock: socket.socket) -> str:
    first, second = _recv_exact(sock, 2)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if second & 0x80 else None
    payload = _recv_exact(sock, length)
    if mask:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    if opcode == 0x8:
        raise ConnectionError("CDP WebSocket closed")
    if opcode != 0x1:
        return ""
    return payload.decode("utf-8")


def _connect_websocket(url: str, timeout: float) -> socket.socket:
    prefix = "ws://"
    if not url.startswith(prefix):
        raise ValueError(f"unsupported WebSocket URL: {url}")
    authority, path = url[len(prefix) :].split("/", 1)
    host, port_text = authority.rsplit(":", 1)
    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    sock = socket.create_connection((host, int(port_text)), timeout=timeout)
    request = (
        f"GET /{path} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
    if not response.startswith(b"HTTP/1.1 101"):
        sock.close()
        raise ConnectionError(response.split(b"\r\n", 1)[0].decode("ascii", "replace"))
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    )
    if f"Sec-WebSocket-Accept: {accept.decode('ascii')}".lower().encode() not in response.lower():
        sock.close()
        raise ConnectionError("invalid CDP WebSocket handshake")
    return sock


def install_workaround(timeout: float = 2.0) -> None:
    with urllib.request.urlopen(CDP_LIST_URL, timeout=timeout) as response:
        targets = json.load(response)
    target = next(
        (
            item
            for item in targets
            if item.get("type") == "page"
            and "browserType=4" in item.get("url", "")
            and "browserviewpopup" not in item.get("url", "")
        ),
        None,
    )
    if target is None:
        raise RuntimeError("Steam Gamepad UI CDP target not found")

    sock = _connect_websocket(target["webSocketDebuggerUrl"], timeout)
    try:
        _send_text(
            sock,
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": INSTALL_WORKAROUND,
                        "returnByValue": True,
                    },
                }
            ),
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = _recv_text(sock)
            if not message:
                continue
            result = json.loads(message)
            if result.get("id") != 1:
                continue
            exception = result.get("result", {}).get("exceptionDetails")
            if exception:
                raise RuntimeError(exception.get("text", "Steam UI injection failed"))
            return
        raise TimeoutError("Steam UI did not answer the CDP request")
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("menu", choices=("main", "quick"))
    parser.add_argument(
        "--gamepad-script",
        default=os.environ.get(
            "STEAM_GAMEPAD_SHORTCUT_SCRIPT",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "steam-gamepad-shortcut.py"),
        ),
    )
    args = parser.parse_args()

    try:
        install_workaround()
    except Exception as error:
        print(f"steam-side-menu: opaque menu workaround unavailable: {error}", file=os.sys.stderr)

    shortcut = "home" if args.menu == "main" else "home+a"
    return subprocess.run([args.gamepad_script, shortcut], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
