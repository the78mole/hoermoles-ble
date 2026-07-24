# Hoermoles

Independent control of Hoermann garage door drives that use the BlueSecur BLE
"Signed" protocol, without relying on the official app/cloud.

## Layout

- `python/` - uv workspace with the Python packages:
  - `hoermoles-ble` - protocol/crypto core + BLE client (`packages/hoermoles-ble`)
  - `hoermoles-ble-cli` - test tool/CLI (`packages/hoermoles-ble-cli`)
  - `hoermoles-ble-homeassistant` - Home Assistant integration (placeholder, not implemented yet)

Planned, not yet started: our own single-page app, plus ports of the
protocol library to other languages (see `python/packages/hoermoles-ble/src/hoermoles_ble/protocol.py`
as the dependency-free reference implementation).

## Quickstart

```bash
uv tool install hoermoles-ble-cli
hoermoles-ble scan
```

Working on this repo instead? `cd python && uv sync`, then prefix commands
with `uv run` - see `python/README.md`.
