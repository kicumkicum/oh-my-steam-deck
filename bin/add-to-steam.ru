#!/usr/bin/env python3
import os
import sys
import re
from pathlib import Path
import shutil
import vdf
from tabulate import tabulate

# TODO Add banners from banner_vertical.png, banner_horizontal.png to game in steam library

# ------------------ Работа с Steam ------------------

def get_steam_userdata_dir():
    home = Path.home()
    candidates = [
        home / ".steam/steam/userdata",
        home / ".local/share/Steam/userdata",
        home / "Library/Application Support/Steam/userdata",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Steam/userdata",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("❌ Не удалось найти папку Steam userdata")

def find_shortcuts_vdf():
    userdata = get_steam_userdata_dir()
    for userdir in userdata.iterdir():
        if userdir.is_dir():
            config = userdir / "config" / "shortcuts.vdf"
            if config.exists():
                return config
    raise FileNotFoundError("❌ Файл shortcuts.vdf не найден")

def read_shortcuts(path):
    with open(path, "rb") as f:
        return vdf.binary_load(f)

def write_shortcuts(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        vdf.binary_dump(data, f)

# ------------------ Игры ------------------

def sanitize_game_name(name: str) -> str:
    name = re.sub(r"\[.*?\]|\(.*?\)|-[^-]+$", "", name)
    name = name.replace("_", " ").replace(".", " ").replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name.strip()

def scan_games(folder):
    games = []
    no_exec_dirs = []
    for entry in os.scandir(folder):
        if not entry.is_dir():
            continue
        exe_found = False
        for root, _, files in os.walk(entry.path):
            for f in files:
                if f.endswith((".exe", ".sh", ".AppImage")):
                    exe_found = True
                    full_path = os.path.join(root, f)
                    games.append({
                        "AppName": entry.name,
                        "Exe": f"\"{full_path}\"",
                        "StartDir": f"\"{root}\"",
                        "ShortcutPath": "",
                        "LaunchOptions": "",
                        "IsHidden": 0,
                        "AllowDesktopConfig": 1,
                        "OpenVR": 0,
                        "Devkit": 0,
                        "DevkitGameID": "",
                        "LastPlayTime": 0,
                        "tags": {}
                    })
                    break
            if exe_found:
                break
        if not exe_found:
            no_exec_dirs.append(entry.name)
    return games, no_exec_dirs

def game_exists(existing, exe_path):
    for shortcut in existing.values():
        if shortcut.get("Exe", "").strip('"') == exe_path:
            return True
    return False

def find_banners(game_folder):
    """
    Ищет конкретные файлы баннеров в папке игры.
    Возвращает пути (горизонтальный, вертикальный), либо пустые строки.
    """
    horizontal = os.path.join(game_folder, "banner_horizontal.png")
    vertical = os.path.join(game_folder, "banner_vertical.png")
    return (horizontal if os.path.isfile(horizontal) else "",
            vertical if os.path.isfile(vertical) else "")

# ------------------ Основная логика ------------------

def main():
    if len(sys.argv) < 2:
        print("Использование: python add-to-steam.py /путь/к/папке/с/играми")
        sys.exit(1)

    folder = Path(sys.argv[1]).expanduser().resolve()
    if not folder.is_dir():
        print(f"❌ Ошибка: {folder} — не папка.")
        sys.exit(1)

    try:
        shortcuts_path = find_shortcuts_vdf()
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)

    shortcuts = read_shortcuts(shortcuts_path)
    existing = shortcuts.get("shortcuts", {})

    next_index = max(map(int, existing.keys()), default=-1) + 1
    results = []

    games, no_exec_dirs = scan_games(folder)

    # папка для баннеров
    grid_path = None
    userdata = get_steam_userdata_dir()
    for userdir in userdata.iterdir():
        if userdir.is_dir():
            grid_path_candidate = userdir / "config" / "grid"
            grid_path_candidate.mkdir(parents=True, exist_ok=True)
            grid_path = grid_path_candidate
            break
    if grid_path is None:
        print("❌ Не удалось определить папку для баннеров Steam")
        sys.exit(1)

    for game in games:
        exe_path = game["Exe"].strip('"')
        old_name = game["AppName"]
        new_name = sanitize_game_name(old_name)

        if game_exists(existing, exe_path):
            results.append(["🟡 Уже есть", old_name, new_name, ""])
        else:
            app_id = str(next_index)
            # используем очищенное имя
            game["AppName"] = new_name
            existing[app_id] = game
            next_index += 1
            status = "✅ Добавлена"

            horizontal, vertical = find_banners(Path(exe_path).parent)

            # копируем баннеры в Steam grid
            horizontal_path_str = ""
            vertical_path_str = ""
            if horizontal:
                dest = grid_path / f"{app_id}_horizontal.png"
                shutil.copy2(horizontal, dest)
                horizontal_path_str = str(dest)
            if vertical:
                dest = grid_path / f"{app_id}_vertical.png"
                shutil.copy2(vertical, dest)
                vertical_path_str = str(dest)

            banner_paths = ", ".join(p for p in [horizontal_path_str, vertical_path_str] if p)
            if banner_paths:
                status += " + баннеры"

            results.append([status, old_name, new_name, banner_paths])

    for name in no_exec_dirs:
        results.append(["⚠️ Не найден исполняемый файл", name, "", ""])

    if any("✅" in r[0] for r in results):
        write_shortcuts(shortcuts_path, shortcuts)

    print(tabulate(results, headers=["Статус", "Старое имя", "Новое имя", "Путь до баннеров"], tablefmt="grid", stralign="center"))
    added_count = sum(1 for r in results if "✅" in r[0])
    if added_count:
        print(f"\n✅ Добавлено {added_count} новых игр. Перезапусти Steam, чтобы они появились.")
    else:
        print("\n🎮 Новых игр не добавлено.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("❌ Ошибка в скрипте:")
        traceback.print_exc()
        sys.exit(1)