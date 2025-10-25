#!/bin/bash
set -e

EGPU_PCI="0000:03:00.0"
UNBIND_PATH="/sys/bus/pci/devices/$EGPU_PCI/driver/unbind"
BIND_PATH="/sys/bus/pci/drivers/amdgpu/bind"

CACHE_LINK="$HOME/.steam/steam/steamapps/shadercache"
EGPU_CACHE="$HOME/.steam/steam/steamapps/shadercache_egpu"
IGPU_CACHE="$HOME/.steam/steam/steamapps/shadercache_igpu"

switch_shadercache() {
  case "$1" in
    egpu)
      echo "[egpu] Переключение shadercache на eGPU..."
      # Создаем директории, если их нет
      [ -d "$EGPU_CACHE" ] || mkdir -p "$EGPU_CACHE"
      [ -L "$CACHE_LINK" ] && rm -f "$CACHE_LINK"
      ln -s "$EGPU_CACHE" "$CACHE_LINK"
      ;;
    igpu)
      echo "[egpu] Переключение shadercache на iGPU..."
      [ -d "$IGPU_CACHE" ] || mkdir -p "$IGPU_CACHE"
      [ -L "$CACHE_LINK" ] && rm -f "$CACHE_LINK"
      ln -s "$IGPU_CACHE" "$CACHE_LINK"
      ;;
  esac
}

GPU_COUNT=$(lspci | grep -i 'VGA\|3D' | wc -l)
if [ "$GPU_COUNT" -lt 2 ]; then
    echo "Найдено меньше двух видеокарт ($GPU_COUNT). Переключаем shadercache на iGPU и выходим."
    switch_shadercache igpu
    exit 0
fi

(
# Ждем пока файл unbind станет доступен
while [ ! -w "$UNBIND_PATH" ]; do
    sleep 1
done

echo "$EGPU_PCI" > "$UNBIND_PATH"

sleep 10
echo "$EGPU_PCI" > "$BIND_PATH"

# После привязки eGPU переключаем shadercache на eGPU
switch_shadercache egpu
) &