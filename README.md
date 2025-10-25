# Oh my Steam Deck

A set of scripts, settings and game fixes.

[Русская версия](README.ru.md)

## First steps

### Enable SSH

- Set password: `passwd`
- Enable SSH: `sudo systemctl enable sshd --now`

### Save your games and saves

When Steam resets the system, it removes the `~/.local` directory with your games, saves and settings. You can save games and saves:

- If you don't have any installed games - install any game first
- `mkdir ~/games`
- `mv ~/.local/share/Steam/steamapps/common/ ~/games/steam`
- `ln -s ~/games/steam ~/.local/share/Steam/steamapps/common`
- `mv ~/.local/share/Steam/steamapps/compatdata/ ~/games/steam-saves`
- `ln -s ~/games/steam-saves ~/.local/share/Steam/steamapps/compatdata`

## Extend libraries

### Add a directory from another disk as a library

Run script from bin directory from repo via SSH: `./bin/add-external-library /some/path/library`

### Add a remote directory via NFS

1. Install NFS `TODO`
2. Run script `TODO`

### Add other games to library

Script for adding all games in some directory to Steam library `TODO`

## Games workarounds

### Baldur's Gate 3 Enable Split Screen

Source - https://www.reddit.com/r/SteamDeck/comments/15iiyxb/baldurs_gate_3_split_screen_solution/

1. Go to properties and set launch argument to: SteamDeck=0 %command%
2. Also recommend to add --skip-launcher after the first launch.

### Kill la Kill - IF Fix launching

Source - https://gist.github.com/bkacjios/649227c6691d2f49faaba871a11e351b

1. Save patch next to `KILLlaKILL_IF.exe`.
2. Run and apply patch

```sh
#!/bin/bash

# Define color codes
RED="\e[31m"
YELLOW="\e[33m"
GREEN="\e[32m"
CYAN="\e[36m"
RESET="\e[0m"

# Define the filename of the EXE
exe_file="KILLlaKILL_IF.exe"

# Check if the executable exists in the current directory
if [ ! -f "$exe_file" ]; then
    echo -e "${RED}Error: $exe_file not found in the current directory!${RESET}"
    exit 1
fi

# Define the hex patterns
original_hex="cc08c89088010000"
patched_hex="cc08c89000000000"

# Check for the patterns in the executable
if xxd -p "$exe_file" | grep -q "$original_hex"; then
    echo -e "${GREEN}The executable contains the original launcher style.${RESET}"
    read -p "Would you like to patch it to work on the steam deck? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        cp "$exe_file" "${exe_file}.bak"  # Backup before modifying
        echo -e "${CYAN}Backup created: ${exe_file}.bak${RESET}"
        xxd -p "$exe_file" | sed "s/$original_hex/$patched_hex/g" | xxd -r -p > "${exe_file}.patched"
        mv "${exe_file}.patched" "$exe_file"
        echo -e "${GREEN}The executable has been patched.${RESET}"
    else
        echo "No changes made."
    fi
elif xxd -p "$exe_file" | grep -q "$patched_hex"; then
    echo -e "${YELLOW}Warning: The executable is already patched so the launcher works on the steam deck.${RESET}"
    read -p "Would you like to unpatch it? (y/n): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        cp "$exe_file" "${exe_file}.bak"  # Backup before modifying
        echo -e "${CYAN}Backup created: ${exe_file}.bak${RESET}"
        xxd -p "$exe_file" | sed "s/$patched_hex/$original_hex/g" | xxd -r -p > "${exe_file}.unpatched"
        mv "${exe_file}.unpatched" "$exe_file"
        echo -e "${GREEN}The executable has been unpatched.${RESET}"
    else
        echo "No changes made."
    fi
else
    echo -e "${RED}Error: Neither the original nor patched value was found in the executable.${RESET}"
fi
```

## Mount NFS share and use it as a library

TODO

## Add external GPU

### Hardware

- M2-oculink adapter instead of SSD
- Oculink to PCI-e adapter

### Install system on MicroSD

Script https://github.com/kicumkicum/SteamOS-microSD
- [ ] Blocked call sanitize in original Valve script

### Debug

lspci |grep VGA
journalctl --user -u gamescope-session.service -b

TODO
