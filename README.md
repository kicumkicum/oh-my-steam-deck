# Oh my Steam Deck

A set of scripts, settings and game fixes.

## First steps

### Save your games and saves

When steam reset system, it remove `~/.local` directory wyth your games, saves and settings. You can safe games and saves

- If you dont have any installed games - install any game first
- `mkdir ~/games`
- `mv ~/.local/share/Steam/steamapps/common/ ~/games/steam`
- `ln -s ~/games/steam ~/.local/share/Steam/steamapps/common/`
- `mv ~/.local/share/Steam/steamapps/compatdata/ ~/games/steam-saves`
- `ln -s ~/games/steam-saves ~/.local/share/Steam/steamapps/compatdata/`

## Games workarounds

### Baldurs Gate's 3 Enable Split Screen

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

## Mount NFS share and use it like library

TODO

## Add external GPU

### Hardware

- M2-oculink adapter instead of ssd
- Oculink to pci-e adapter

### Install system on MicroSD

Script https://github.com/kicumkicum/SteamOS-microSD
- [ ] Blocked call sanitize in original valve script

TODO
