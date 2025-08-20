#!/bin/bash
set -e

EGPU_PCI="0000:03:00.0"
UNBIND_PATH="/sys/bus/pci/devices/$EGPU_PCI/driver/unbind"
BIND_PATH="/sys/bus/pci/drivers/amdgpu/bind"

GPU_COUNT=$(lspci | grep -i 'VGA\|3D' | wc -l)
if [ "$GPU_COUNT" -lt 2 ]; then
    echo "Найдено меньше двух видеокарт ($GPU_COUNT). Выходим."
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
) &
