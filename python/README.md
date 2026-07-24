# hoermoles-ble workspace

A `uv` workspace with the `hoermoles-ble` protocol/BLE library and the
`hoermoles-ble-cli` command-line tool for controlling a Hoermann garage door
drive over its BlueSecur BLE "Signed" protocol - independent of the official
app or cloud service.

See the [project root README](../README.md) for the overall repo layout.

## Packages

| Package | Description |
|---|---|
| [`hoermoles-ble`](packages/hoermoles-ble) | Protocol/crypto core + BLE client. `protocol.py` has no third-party dependencies and serves as a template for ports to other languages. |
| [`hoermoles-ble-cli`](packages/hoermoles-ble-cli) | CLI tool (`hoermoles-ble` command) built on top of the library. |
| [`hoermoles-ble-homeassistant`](packages/hoermoles-ble-homeassistant) | Home Assistant custom component - placeholder, not implemented yet. |

## Requirements

- Python >= 3.10
- [`uv`](https://docs.astral.sh/uv/)
- Linux with BlueZ for the real BLE transport (`bleak`); macOS/Windows are
  supported by `bleak` itself but untested here.

## Setup

```bash
cd python
uv sync
```

## Configuration

Credentials and saved QR codes are stored under a config directory, resolved
in this order:

1. `--config-dir` command-line argument
2. Environment variable `HOERMOLES_CONF_DIR`
3. `HOERMOLES_CONF_DIR` from a `.env` file (searched upward from the current
   directory)
4. Default: `~/.hoermoles`

Layout under the config directory:

```
<config-dir>/
├── qr_codes.txt              one QR code content per line (see save-qr below)
├── devices.json              MAC -> product_class/product_id/product_name/serial_no
│                             for every drive seen via 'scan' or 'register' (no secrets)
└── credentials/
    └── <MAC-with-dashes>.json   RootID + root key for one drive
```

## Usage

Just want the CLI, not a full checkout of this repo? `uv tool install
hoermoles-ble-cli` gives you the `hoermoles-ble` command directly (see
`packages/hoermoles-ble/README.md` for that walkthrough). The rest of this
section assumes you're working from this workspace checkout instead (prefix
every command with `uv run`).

There's no companion app with camera QR scanning yet, so QR code contents
(photographed and typed off, or read with a separate scanner app) are saved
once and matched to a scanned device automatically by the serial number
embedded in both the QR code and the BLE advertisement:

```bash
uv run hoermoles-ble save-qr "<QR code content>"
```

Scan for drives (also shows whether a saved QR code matches, and saves each
drive's product type to the device registry - see `list-devices` below):

```bash
uv run hoermoles-ble scan
```

One-time registration (uses the saved QR code automatically, or pass
`--qr-file`):

```bash
uv run hoermoles-ble register --address F1:26:AF:CC:41:86
```

Trigger a gate action - `impulse` (factory-default toggle), `open`, `close`,
`light`, `partial`, or `ventilation` (see `hoermoles_ble.protocol.GATE_ACTIONS`
for how these map to the drive's channel numbers; only `impulse` has been
verified against real hardware so far):

```bash
uv run hoermoles-ble exec --address F1:26:AF:CC:41:86 open
```

Run `uv run hoermoles-ble --help` or `uv run hoermoles-ble <command> --help`
for the full option list.

List every drive whose product type is known (from `scan`/`register`), and
whether credentials are saved for it too:

```bash
uv run hoermoles-ble list-devices
```

Read/write the drive's numbered operator menus (menu 20 "reversal limit",
menu 52 "speed door open", ...) - see `hoermoles_ble.menu_settings` for the
known products (Supramatic Serie 4/E4, Rollmatic 2, SilentDrive 2, Supramatic
4 H4, HET). The product type must already be in the device registry (run
`scan` near the drive first if `list-devices` doesn't show it yet). Reading
is live-verified against real hardware (Supramatic E4); writing is not yet,
for any product (see `packages/hoermoles-ble/README.md`):

```bash
uv run hoermoles-ble menu-get --address F1:26:AF:CC:41:86       # read every known menu
uv run hoermoles-ble menu-get --address F1:26:AF:CC:41:86 52    # read one menu
uv run hoermoles-ble menu-set --address F1:26:AF:CC:41:86 52=1  # write one menu
```

Read the drive's security/access audit log (who registered, channel
toggles, blocked login attempts, clock changes, ...) and service/diagnostics
counters (operating hours, door cycles, maintenance counters, ...) - see
`hoermoles_ble.device_log`. Live-verified against real hardware:

```bash
uv run hoermoles-ble view-log --address F1:26:AF:CC:41:86
```

## Using the library directly

```python
import asyncio
from hoermoles_ble import Credentials, HoermannClient
from hoermoles_ble.ble_transport import BleakTransport

async def main():
    credentials = Credentials.load_for_device("F1:26:AF:CC:41:86")
    async with HoermannClient(BleakTransport("F1:26:AF:CC:41:86")) as client:
        await client.wait_for_any_notification()
        await client.open_channel(credentials, channel=1)

asyncio.run(main())
```

## License

MIT, see [`../LICENSE`](../LICENSE).
