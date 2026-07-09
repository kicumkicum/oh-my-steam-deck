# amdgpu-fan for SteamOS eGPU

This repository vendors upstream `amdgpu-fan` as a git submodule:

- `libs/amdgpu-fan`
- upstream documentation: https://github.com/chestm007/amdgpu-fan

The local wrapper runs upstream code from `/home/deck/libs/amdgpu-fan` without
installing it as a system Python package. The systemd unit lives in
`/etc/systemd/system/amdgpu-fan.service` so it is less likely to be overwritten
by SteamOS updates than a package-owned unit in `/usr/lib/systemd/system`.

## Files

- `bin/amdgpu-fan.install` installs the submodule copy, wrapper, config, and
  systemd unit.
- `bin/amdgpu-fan.boot.sh` runs upstream `amdgpu-fan` with `PYTHONPATH`.
- `bin/amdgpu-fan-detect.sh` lists DRM cards, PCI IDs, hwmon temperatures, fan
  RPM, and PWM files.
- `bin/amdgpu-fan.yml` is the default config copied to `/etc/amdgpu-fan.yml`
  only when no config exists yet.
- `bin/amdgpu-fan.service` is the local systemd unit.

## Install

Initialize the submodule if needed:

```sh
git submodule update --init --recursive
```

Install Python dependencies on SteamOS/Arch:

```sh
sudo pacman -S python-numpy python-yaml
```

If SteamOS readonly mode blocks package installation:

```sh
sudo steamos-readonly disable
sudo pacman -S python-numpy python-yaml
```

Run the installer from the repository root:

```sh
./bin/amdgpu-fan.install
```

Review the detected cards and config:

```sh
/home/deck/bin/amdgpu-fan-detect.sh
sudo nano /etc/amdgpu-fan.yml
```

Start the service:

```sh
sudo systemctl start amdgpu-fan.service
systemctl status --no-pager -l amdgpu-fan.service
```

Enable at boot is done by the install script:

```sh
sudo systemctl enable amdgpu-fan.service
```

## Configuration

`/etc/amdgpu-fan.yml` uses upstream's `speed_matrix` format:

```yaml
speed_matrix:
- [0, 20]
- [45, 28]
- [55, 40]
- [65, 55]
- [75, 75]
- [82, 100]
temp_drop: 5
```

The first value is temperature in Celsius. The second value is fan duty in
percent. Upstream interpolates between points.

If the machine has both iGPU and eGPU, card numbers can change. Use
`amdgpu-fan-detect.sh` and optionally pin the external GPU:

```yaml
cards:
- card0
```

## Temperature Source

Upstream `amdgpu-fan` reads `temp1_input`, which is usually AMDGPU `edge`
temperature. It does not use `junction`/hotspot by default. Compare with:

```sh
sensors
```

For RX 6600, a conservative edge-based curve is acceptable, but monitor
`junction` under load. If hotspot stays too high, make the edge curve more
aggressive.

## Stop And Restore Auto Fan

Stop the daemon:

```sh
sudo systemctl stop amdgpu-fan.service
```

Most AMD cards return to automatic fan control when `pwm1_enable` is set to `2`:

```sh
for f in /sys/class/drm/card*/device/hwmon/hwmon*/pwm1_enable; do
  echo 2 | sudo tee "$f"
done
```
