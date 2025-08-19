#!/bin/bash
set -e

# eGPU ID
EGPU_PCI="0000:03:00.0"

unbind_path="/sys/bus/pci/devices/$EGPU_PCI/driver/unbind"
bind_path="/sys/bus/pci/drivers/amdgpu/bind"

# Remove eGPU
echo "$EGPU_PCI" > "$unbind_path"

# Add eGPU after 10 sec (in backgroud)
(
  sleep 10
  echo "$EGPU_PCI" > "$bind_path"
) &
