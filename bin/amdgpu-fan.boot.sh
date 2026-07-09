#!/bin/bash
set -euo pipefail

# Run upstream amdgpu-fan from the copy installed by amdgpu-fan.install.
# The upstream daemon reads /etc/amdgpu-fan.yml and writes the selected PWM
# value to the AMDGPU hwmon sysfs files once per second.

AMDGPU_FAN_HOME="/home/deck/libs/amdgpu-fan"

if [ ! -d "$AMDGPU_FAN_HOME/amdgpu_fan" ]; then
    echo "amdgpu-fan source not found at $AMDGPU_FAN_HOME" >&2
    echo "Run ./bin/amdgpu-fan.install from this repository first." >&2
    exit 1
fi

if ! /usr/bin/python - <<'PY' >/dev/null 2>&1
import numpy
import yaml
PY
then
    echo "Missing Python dependencies: numpy and/or PyYAML." >&2
    echo "Install python-numpy and python-yaml, then restart amdgpu-fan.service." >&2
    exit 1
fi

export PYTHONPATH="$AMDGPU_FAN_HOME:${PYTHONPATH:-}"
exec /usr/bin/python -m amdgpu_fan.controller
