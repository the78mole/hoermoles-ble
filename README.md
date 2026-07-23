# Hoermoles

Independent control of Hoermann garage door drives that use the BlueSecur BLE
"Signed" protocol, without relying on the official app/cloud.

## Layout

- `python/` - uv workspace with the Python packages:
  - `hoermoles-ble` - protocol/crypto core + BLE client (`packages/hoermoles-ble`)
  - `hoermoles-ble-cli` - test tool/CLI (`packages/hoermoles-ble-cli`)
  - `hoermoles-ble-homeassistant` - Home Assistant integration (placeholder, not implemented yet)
- `reveng/` - reverse-engineering material (APK/XAPK, decompiles, analysis notes,
  QR code, photos, Bluetooth log). **Not tracked in git** (see `.gitignore`) -
  purely local working material, not part of the product.

Planned, not yet started: our own single-page app, plus ports of the
protocol library to other languages (see `python/packages/hoermoles-ble/src/hoermoles_ble/protocol.py`
as the dependency-free reference implementation).

## Quickstart

```bash
cd python
uv sync
uv run hoermoles-ble scan
```
