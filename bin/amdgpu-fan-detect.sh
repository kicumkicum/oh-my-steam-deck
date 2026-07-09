#!/bin/bash
set -euo pipefail

# Print AMD DRM cards, their PCI address, hwmon name, readable temperatures,
# fan speed, and PWM control files. Use this before editing /etc/amdgpu-fan.yml
# because card numbers can change when the iGPU/eGPU enumeration order changes.

for card_path in /sys/class/drm/card[0-9]*; do
    [ -e "$card_path/device" ] || continue

    card="$(basename "$card_path")"
    pci_path="$(readlink -f "$card_path/device")"
    pci_id="$(basename "$pci_path")"
    vendor="$(cat "$card_path/device/vendor" 2>/dev/null || true)"
    device="$(cat "$card_path/device/device" 2>/dev/null || true)"

    printf "\n%s\n" "$card"
    printf "  pci: %s\n" "$pci_id"
    printf "  ids: vendor=%s device=%s\n" "$vendor" "$device"

    for hwmon in "$card_path"/device/hwmon/hwmon*; do
        [ -d "$hwmon" ] || continue
        printf "  hwmon: %s name=%s\n" "$hwmon" "$(cat "$hwmon/name" 2>/dev/null || true)"

        for temp in "$hwmon"/temp*_input; do
            [ -f "$temp" ] || continue
            label="${temp%_input}_label"
            name="$(cat "$label" 2>/dev/null || basename "$temp")"
            value="$(awk '{printf "%.1f C", $1 / 1000}' "$temp" 2>/dev/null || true)"
            printf "    temp: %s = %s\n" "$name" "$value"
        done

        for fan in "$hwmon"/fan*_input; do
            [ -f "$fan" ] || continue
            printf "    fan: %s RPM\n" "$(cat "$fan" 2>/dev/null || true)"
        done

        for pwm in "$hwmon"/pwm*; do
            [ -f "$pwm" ] || continue
            printf "    pwm: %s = %s\n" "$(basename "$pwm")" "$(cat "$pwm" 2>/dev/null || true)"
        done
    done
done
