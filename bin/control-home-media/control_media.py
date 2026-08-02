#!/usr/bin/env python3
# Version: 1
import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


class UserError(RuntimeError):
    pass


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, text=True, capture_output=True, check=check)
    except FileNotFoundError as e:
        raise UserError(f"Не найдена команда `{e.filename}`.") from e


def _load_config(path: str | None) -> dict[str, Any]:
    if not path:
        path = os.environ.get("CONTROL_MEDIA_CONFIG") or os.path.join(
            os.path.dirname(__file__), "control_media.config.json"
        )
    if not os.path.exists(path):
        raise UserError(
            "Не найден конфиг. Укажи --config или создай `control_media.config.json` "
            f"(ожидался: {path})."
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise UserError(f"Конфиг не является валидным JSON: {e}") from e


def _get_device_cfg(cfg: dict[str, Any], device_type: str, device_id: str) -> dict[str, Any]:
    section = cfg.get(device_type)
    if not isinstance(section, dict):
        raise UserError(f"В конфиге нет секции `{device_type}`.")
    dev = section.get(device_id)
    if not isinstance(dev, dict):
        known = ", ".join(sorted(section.keys())) if section else ""
        raise UserError(
            f"Устройство `{device_type}` с id `{device_id}` не найдено в конфиге."
            + (f" Известные id: {known}" if known else "")
        )
    return dev


def _ensure_adb_connected(serial: str) -> None:
    # For TCP ADB: "ip:port". For USB: any serial is fine; "adb -s <serial>" will work.
    if ":" in serial:
        proc = _run(["adb", "connect", serial], check=False)
        out = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            raise UserError(f"adb connect не удался: {out}")


def _adb_shell(serial: str, cmd: str) -> str:
    _ensure_adb_connected(serial)
    proc = _run(["adb", "-s", serial, "shell", cmd], check=False)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        raise UserError(f"adb shell ошибка: {out}")
    return out


def _adb_keyevent(serial: str, keycode: int, count: int = 1) -> None:
    if count <= 0:
        return
    for _ in range(count):
        _adb_shell(serial, f"input keyevent {keycode}")


def _tv_set_source(device_id: str, dev_cfg: dict[str, Any], kind: str, name: str) -> None:
    if kind == "application":
        apps = dev_cfg.get("apps") or {}
        app = apps.get(name)
        if not isinstance(app, dict):
            known = ", ".join(sorted(apps.keys())) if isinstance(apps, dict) else ""
            raise UserError(
                f"Приложение `{name}` не найдено в конфиге tv.apps."
                + (f" Известные: {known}" if known else "")
            )
        package = app.get("package")
        activity = app.get("activity")
        if not package:
            raise UserError(f"Для tv.apps.{name} нужно указать `package`.")
        if activity:
            _adb_shell(device_id, f"am start -n {shlex.quote(package + '/' + activity)}")
        else:
            # Use monkey to launch main activity reliably
            _adb_shell(device_id, f"monkey -p {shlex.quote(package)} -c android.intent.category.LAUNCHER 1")
        return

    if kind == "input":
        inputs = dev_cfg.get("inputs") or {}
        inp = inputs.get(name)
        if not isinstance(inp, dict):
            known = ", ".join(sorted(inputs.keys())) if isinstance(inputs, dict) else ""
            raise UserError(
                f"Вход `{name}` не найден в конфиге tv.inputs."
                + (f" Известные: {known}" if known else "")
            )

        # 1) preferred: intent with data URI
        intent = inp.get("intent")
        if intent:
            _adb_shell(device_id, f"am start -a android.intent.action.VIEW -d {shlex.quote(intent)}")
            return

        # 2) fallback: keyevents sequence (e.g. open input menu)
        keyevents = inp.get("keyevents")
        if isinstance(keyevents, list) and all(isinstance(x, int) for x in keyevents):
            for kc in keyevents:
                _adb_keyevent(device_id, kc, 1)
            return

        raise UserError(
            f"Для tv.inputs.{name} нужно указать `intent` или `keyevents`."
        )

    raise UserError("kind должен быть `input` или `application` для tv.")


def _tv_set_volume(device_id: str, dev_cfg: dict[str, Any], level: int | None, delta: int | None) -> None:
    if level is None and delta is None:
        raise UserError("Нужно указать --level или --delta.")
    if level is not None and delta is not None:
        raise UserError("Укажи только одно: --level или --delta.")

    # Absolute volume: best-effort via Android's cmd/media helpers if present.
    if level is not None:
        stream = int(dev_cfg.get("volume_stream", 3))  # 3 = STREAM_MUSIC
        # Try common variants; ignore failures until last.
        attempts = [
            f"cmd media_session volume --stream {stream} --set {level}",
            f"cmd media_session volume --set {level}",
            f"media volume --stream {stream} --set {level}",
        ]
        last_err: str | None = None
        for a in attempts:
            proc = _run(["adb", "-s", device_id, "shell", a], check=False)
            if proc.returncode == 0:
                return
            last_err = (proc.stdout + proc.stderr).strip()
        raise UserError(
            "Не удалось выставить абсолютную громкость через adb (на этой прошивке/версии Android команды могут отличаться). "
            f"Последняя ошибка: {last_err}"
        )

    # Relative: keyevents.
    if delta is not None:
        if delta > 0:
            _adb_keyevent(device_id, 24, delta)  # KEYCODE_VOLUME_UP
        elif delta < 0:
            _adb_keyevent(device_id, 25, -delta)  # KEYCODE_VOLUME_DOWN
        return


@dataclass(frozen=True)
class ReceiverTarget:
    ip: str
    port: int
    zone: str


def _parse_receiver_target(device_id: str, dev_cfg: dict[str, Any]) -> ReceiverTarget:
    # device_id is usually IP; port/zone are configurable
    port = int(dev_cfg.get("port", 10025))
    zone = str(dev_cfg.get("zone", "Main Zone"))
    return ReceiverTarget(ip=device_id, port=port, zone=zone)


def _receiver_php(script_dir: str) -> str:
    return os.path.join(script_dir, "harman-kardon-remote", "control.php")


def _php_binary() -> str:
    return os.environ.get("CONTROL_MEDIA_PHP") or "php"


def _receiver_set_source(device_id: str, dev_cfg: dict[str, Any], source: str) -> None:
    sources = dev_cfg.get("sources") or {}
    mapped = sources.get(source, source)
    if not isinstance(mapped, str) or not mapped:
        raise UserError("Некорректный source для receiver (проверь receiver.sources в конфиге).")

    script_dir = os.path.dirname(__file__)
    php_script = _receiver_php(script_dir)
    if not os.path.exists(php_script):
        raise UserError(f"Не найден `{php_script}` (ожидается рядом с проектом).")

    target = _parse_receiver_target(device_id, dev_cfg)
    proc = _run(
        [
            _php_binary(),
            php_script,
            "--id",
            target.ip,
            "--port",
            str(target.port),
            "--zone",
            target.zone,
            "--source",
            mapped,
        ],
        check=False,
    )
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        raise UserError(out or "receiver: ошибка выполнения php скрипта")


def _receiver_set_volume(device_id: str, dev_cfg: dict[str, Any], delta: int) -> None:
    script_dir = os.path.dirname(__file__)
    php_script = _receiver_php(script_dir)
    if not os.path.exists(php_script):
        raise UserError(f"Не найден `{php_script}` (ожидается рядом с проектом).")

    target = _parse_receiver_target(device_id, dev_cfg)
    proc = _run(
        [
            _php_binary(),
            php_script,
            "--id",
            target.ip,
            "--port",
            str(target.port),
            "--zone",
            target.zone,
            "--delta",
            str(delta),
        ],
        check=False,
    )
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        raise UserError(out or "receiver: ошибка выполнения php скрипта")

def _receiver_fix_firmware(device_id: str, dev_cfg: dict[str, Any], file_path: str, field: str | None) -> None:
    if not os.path.exists(file_path):
        raise UserError(f"Файл не найден: {file_path}")
    if not os.path.isfile(file_path):
        raise UserError(f"Это не файл: {file_path}")

    fix_cfg = dev_cfg.get("fix_firmware") if isinstance(dev_cfg.get("fix_firmware"), dict) else {}
    url = (fix_cfg.get("url") if isinstance(fix_cfg, dict) else None) or f"http://{device_id}/goform/formPostHandler"
    origin = (fix_cfg.get("origin") if isinstance(fix_cfg, dict) else None) or f"http://{device_id}"
    referer = (fix_cfg.get("referer") if isinstance(fix_cfg, dict) else None) or f"http://{device_id}/1000/bl_firmware_update.asp"
    user_agent = (fix_cfg.get("user_agent") if isinstance(fix_cfg, dict) else None) or (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
    )
    form_field = field or (fix_cfg.get("field") if isinstance(fix_cfg, dict) else None) or "file"

    # We rely on curl to build correct multipart/form-data boundary and content-length.
    cmd = [
        "curl",
        url,
        "-X",
        "POST",
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "-H",
        "Accept-Language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "-H",
        "Cache-Control: max-age=0",
        "-H",
        f"Origin: {origin}",
        "-H",
        f"Referer: {referer}",
        "-H",
        "Upgrade-Insecure-Requests: 1",
        "-H",
        f"User-Agent: {user_agent}",
        "--compressed",
        "--insecure",
        "-sS",
        "-f",
        "-F",
        f"{form_field}=@{file_path};type=text/plain",
    ]

    proc = _run(cmd, check=False)
    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        raise UserError(out or "fix-firmware: curl вернул ошибку")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="control_media", add_help=True)
    p.add_argument("--type", required=True, choices=["tv", "receiver"], help="Тип устройства")
    p.add_argument("--id", required=True, help="Адрес/ID (для Android TV обычно ADB serial: ip:5555)")
    p.add_argument("--config", default=None, help="Путь к JSON конфигу (по умолчанию: ./control_media.config.json)")

    sub = p.add_subparsers(dest="command", required=True)

    p_source = sub.add_parser("set-source", help="Установить источник/приложение")
    p_source.add_argument("--kind", choices=["input", "application"], help="Для tv: input|application")
    p_source.add_argument("--name", help="Для tv: имя из конфига (tv.inputs или tv.apps)")
    p_source.add_argument("--source", help="Для receiver: имя источника (маппится через receiver.sources)")

    p_vol = sub.add_parser("set-volume", help="Установить громкость")
    p_vol.add_argument("--level", type=int, help="Для tv: абсолютный уровень (best-effort через adb)")
    p_vol.add_argument("--delta", type=int, help="Для tv: относительное изменение (в шагах); для receiver: только delta")

    p_fix = sub.add_parser("fix-firmware", help="Отправить текстовый файл в web UI ресивера (goform)")
    p_fix.add_argument("--file", required=True, help="Путь к текстовому файлу, который отправлялся с формы")
    p_fix.add_argument(
        "--field",
        default=None,
        help="Имя поля multipart (по умолчанию берётся из конфига receiver.<id>.fix_firmware.field или 'file')",
    )

    args = p.parse_args(argv)
    cfg = _load_config(args.config)
    dev_cfg = _get_device_cfg(cfg, args.type, args.id)

    if args.type == "tv":
        if args.command == "set-source":
            if not args.kind or not args.name:
                raise UserError("Для tv нужно указать `set-source --kind ... --name ...`.")
            _tv_set_source(args.id, dev_cfg, args.kind, args.name)
            return 0
        if args.command == "set-volume":
            _tv_set_volume(args.id, dev_cfg, args.level, args.delta)
            return 0

    if args.type == "receiver":
        if args.command == "set-source":
            if not args.source:
                raise UserError("Для receiver нужно указать `set-source --source ...`.")
            _receiver_set_source(args.id, dev_cfg, args.source)
            return 0
        if args.command == "set-volume":
            if args.delta is None:
                raise UserError("Для receiver поддерживается только `set-volume --delta <steps>` (абсолютной громкости нет).")
            _receiver_set_volume(args.id, dev_cfg, args.delta)
            return 0
        if args.command == "fix-firmware":
            _receiver_fix_firmware(args.id, dev_cfg, args.file, args.field)
            return 0

    raise UserError("Неподдерживаемая комбинация аргументов.")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except UserError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        raise SystemExit(2)
