# Hoermoles

[![PyPI - hoermoles-ble](https://img.shields.io/pypi/v/hoermoles-ble?label=hoermoles-ble)](https://pypi.org/project/hoermoles-ble/)
[![PyPI - hoermoles-ble-cli](https://img.shields.io/pypi/v/hoermoles-ble-cli?label=hoermoles-ble-cli)](https://pypi.org/project/hoermoles-ble-cli/)
[![Release](https://github.com/the78mole/hoermoles-ble/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/the78mole/hoermoles-ble/actions/workflows/pypi-publish.yml)
[![Tests](https://github.com/the78mole/hoermoles-ble/actions/workflows/test.yml/badge.svg)](https://github.com/the78mole/hoermoles-ble/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/the78mole/42b377cb18c21fa8d1cfee3fc3bc3605/raw/hoermoles-ble-coverage.json)](https://github.com/the78mole/hoermoles-ble/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen.svg)](https://renovatebot.com)

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
