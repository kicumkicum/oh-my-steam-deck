# Oh my Steam Deck

Набор скриптов, настроек и исправлений для игр.

[English version](README.md)

## Первые шаги

### Включить SSH

- Установить пароль: `passwd`
- Включить SSH: `sudo systemctl enable sshd --now`

### Не устанавливаются приложения из Discovery

Инструкция - https://boosty.to/steamdecks/posts/2edba56d-9732-44b4-a143-2961b9e843ec

Краткий пересказ. Выполни `bash <(curl -fsSL https://raw.githubusercontent.com/Nospire/fx/main/i)`. Нажми `1`. Следуй инструкциям

### Сохранить игры и сохранения

Когда Steam сбрасывает систему, он удаляет директорию `~/.local` с вашими играми, сохранениями и настройками. Вы можете сохранить игры и сохранения:

- Если у вас нет установленных игр - сначала установите любую игру
- `mkdir ~/games`
- `mv ~/.local/share/Steam/steamapps/common/ ~/games/steam`
- `ln -s ~/games/steam ~/.local/share/Steam/steamapps/common`
- `mv ~/.local/share/Steam/steamapps/compatdata/ ~/games/steam-saves`
- `ln -s ~/games/steam-saves ~/.local/share/Steam/steamapps/compatdata`

## Расширение библиотек

### Добавить директорию с другого диска как библиотеку

Запустить скрипт из папки bin репозитория через SSH: `./bin/add-external-library /some/path/library`

### Добавить удаленную директорию через NFS

1. Установить NFS `TODO`
2. Запустить скрипт `TODO`

### Добавить другие игры в библиотеку

Скрипт для добавления всех игр из некоторой директории в библиотеку Steam `TODO`

## Фиксы для игр

### Baldur's Gate 3 Включить разделенный экран

Источник - https://www.reddit.com/r/SteamDeck/comments/15iiyxb/baldurs_gate_3_split_screen_solution/

1. Перейти в свойства и установить аргумент запуска: SteamDeck=0 %command%
2. Также рекомендуется добавить --skip-launcher после первого запуска.

### Kill la Kill - IF Исправление запуска

Источник - https://gist.github.com/bkacjios/649227c6691d2f49faaba871a11e351b

1. Сохранить патч рядом с `KILLlaKILL_IF.exe`.
2. Запустить и применить патч

```sh
#!/bin/bash

# Определяем цветовые коды
RED="\e[31m"
YELLOW="\e[33m"
GREEN="\e[32m"
CYAN="\e[36m"
RESET="\e[0m"

# Определяем имя файла EXE
exe_file="KILLlaKILL_IF.exe"

# Проверяем, существует ли исполняемый файл в текущей директории
if [ ! -f "$exe_file" ]; then
    echo -e "${RED}Ошибка: $exe_file не найден в текущей директории!${RESET}"
    exit 1
fi

# Определяем hex-паттерны
original_hex="cc08c89088010000"
patched_hex="cc08c89000000000"

# Проверяем паттерны в исполняемом файле
if xxd -p "$exe_file" | grep -q "$original_hex"; then
    echo -e "${GREEN}Исполняемый файл содержит оригинальный стиль лаунчера.${RESET}"
    read -p "Хотите ли вы пропатчить его для работы на Steam Deck? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        cp "$exe_file" "${exe_file}.bak"  # Резервная копия перед изменением
        echo -e "${CYAN}Создана резервная копия: ${exe_file}.bak${RESET}"
        xxd -p "$exe_file" | sed "s/$original_hex/$patched_hex/g" | xxd -r -p > "${exe_file}.patched"
        mv "${exe_file}.patched" "$exe_file"
        echo -e "${GREEN}Исполняемый файл был пропатчен.${RESET}"
    else
        echo "Изменения не внесены."
    fi
elif xxd -p "$exe_file" | grep -q "$patched_hex"; then
    echo -e "${YELLOW}Предупреждение: Исполняемый файл уже пропатчен, поэтому лаунчер работает на Steam Deck.${RESET}"
    read -p "Хотите ли вы отменить патч? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        cp "$exe_file" "${exe_file}.bak"  # Резервная копия перед изменением
        echo -e "${CYAN}Создана резервная копия: ${exe_file}.bak${RESET}"
        xxd -p "$exe_file" | sed "s/$patched_hex/$original_hex/g" | xxd -r -p > "${exe_file}.unpatched"
        mv "${exe_file}.unpatched" "$exe_file"
        echo -e "${GREEN}Патч был отменен.${RESET}"
    else
        echo "Изменения не внесены."
    fi
else
    echo -e "${RED}Ошибка: В исполняемом файле не найдено ни оригинального, ни пропатченного значения.${RESET}"
fi
```

## Монтирование NFS-шары и использование как библиотеки

TODO

## Добавление внешней видеокарты

### Аппаратное обеспечение

- M2-oculink адаптер вместо SSD
- Oculink к PCI-e адаптер

### Установка системы на MicroSD

Скрипт https://github.com/kicumkicum/SteamOS-microSD
- [ ] Заблокирован вызов sanitize в оригинальном скрипте Valve

### Отладка

lspci |grep VGA
journalctl --user -u gamescope-session.service -b

TODO
