# hoermoles-ble

## Getting started: commissioning a drive

Everyday use is via the `hoermoles-ble` CLI (package `hoermoles-ble-cli`,
built on top of this library):

1. `cd python && uv sync` - installs the workspace, including the CLI.

2. Get the QR code sticker's content onto disk - there's no camera-scanning
   app yet, so either read it with a separate scanner app, or take a photo of
   the sticker and decode it with a command-line QR decoder, e.g.
   [`zbarimg`](https://github.com/mchehab/zbar) (`zbarimg --raw photo.jpg`).
   Then save the decoded content once:

   ```bash
   uv run hoermoles-ble save-qr "<QR code content>"
   ```

3. Scan for the drive over BLE - matches the saved QR code by serial number
   and saves the drive's product type to the device registry (see below):

   ```bash
   uv run hoermoles-ble scan
   ```

   Seeing only the short packet ("incompletely parsed", no `Admin taught:
   ...` line) is normal and not a sign of anything - both our own drive
   (already paired) and the official app's own code treat this as a plain
   BLE scan-timing artifact, not something tied to admin/pairing status (the
   decompiled app has explicit, unconditional logic to recover once the
   longer packet eventually arrives - see the local reveng report). Just use
   a longer `--timeout` or retry `scan`.

4. Register (one-time pairing). Only works while the drive still accepts a
   new admin (`AdminsCanBeTeached=True` in the scan output above) - reset via
   the drive's menu 19/parameter 02 first if not (this invalidates the
   existing pairing, e.g. with your phone):

   ```bash
   uv run hoermoles-ble register --address <MAC>
   ```

   This derives and saves the root key under
   `~/.hoermoles/credentials/<MAC>.json` - no QR code, app, or cloud needed
   again afterwards.

5. Trigger the gate:

   ```bash
   uv run hoermoles-ble exec --address <MAC> impulse
   ```

From here on `--address` can usually be omitted (it defaults to the only/
first saved credentials). See `packages/hoermoles-ble-cli/README.md` for the
full command reference (`menu-get`/`menu-set` for operator settings,
`view-log` for the audit log/diagnostics counters, `list-devices`, ...) and
the workspace-level `python/README.md` for a longer walkthrough.

## Library internals

Protocol core (`protocol.py`, `crypto_rsa.py`) and BLE client (`client.py`,
`transport.py`, `ble_transport.py`) for the Hoermann BlueSecur "Signed"
channel.

`protocol.py` deliberately has no third-party dependencies (stdlib only) and
serves as a template for ports to other languages. `bleak` (for the real BLE
transport) is an optional extra: `pip install hoermoles-ble[bleak]`.

Reverse-engineered from the official Hoermann BlueSecur app; see the module
docstrings in `protocol.py`, `client.py`, and `advertisement.py` for details
on where each part of the protocol comes from.

## Operator menu/parameter settings

Besides the channel commands (open/close/light/...), the drive also exposes
its classic numbered configuration menus (menu 20 "reversal limit", menu 25
"operator light", menu 52 "speed door open", ...) over BLE - the same menus
normally set via the hand-transmitter/display sequence, exposed by the
official app as "operator settings". `HoermannClient.read_properties()` and
`.write_properties()` (in `client.py`) read/write these; `menu_settings.py`
provides the menu-number-to-wire-byte table and valid values per menu for
every product the official app knows about (Supramatic Serie 4/E4, Rollmatic
2, SilentDrive 2, Supramatic 4 H4, HET), sourced from the app's own embedded
menu-concept resources, one `DriveMenuTable` per (product_class, product_id)
in `DRIVE_MENU_TABLES`. See the module docstring for the exact
firmware/software scope per product (menu_group wire bytes are NOT
interchangeable across products or even across ProductIDs that share the
same advertised name) and the CLI's `menu-get`/`menu-set` commands for a
ready-to-use example.

The read direction (`read_properties()`/GET_PROPERTIES/GET_SELECTED_PROPERTIES)
is live-verified against a real Supramatic E4 - both a full, unfiltered read
and filtered multi-menu reads returned plausible values. One live-confirmed
protocol quirk: a GET_SELECTED_PROPERTIES request that mixes a menu group <
100 with one >= 100 makes the drive drop the connection instead of
answering - `read_properties()` avoids this via
`protocol.batch_menu_groups_for_selected_properties()`. The write direction
(`write_properties()`/SET_PROPERTIES) is only structurally derived from the
decompiled app and NOT yet confirmed live for any product - read a value back
before writing it, and double-check menu numbers/values against the printed
operator manual.

## Device registry (which product a paired drive is)

`devices.py` keeps a separate `<config_dir>/devices.json` registry mapping
each MAC address to its product_class/product_id/product_name (and serial
number, if known) via `save_device_info()`/`get_device_info()`/
`list_device_infos()` - deliberately not part of `credentials.py`/
`Credentials`, since it's non-secret metadata and, unlike a per-device
credentials file, one file can list every drive ever seen. `scan_devices()`
itself is read-only (no root key needed, nothing persisted) - the CLI's
`scan` command is what saves a `DeviceInfo` for each device it finds with a
decodable product_class/product_id; `register` also saves one directly from
the QR code prefix. `menu-get`/`menu-set` use the registry to pick the right
`DriveMenuTable` automatically.

## Audit log and diagnostics counters

`HoermannClient.read_log()`/`.read_service_data()` (in `client.py`) read the
same two things the app's "log"/diagnostics view shows: a security/access
audit log (who registered, which channel got toggled, blocked login
attempts, clock changes, ...) and service counters (operating hours, door
cycles, maintenance counters, ...) - see `device_log.py` for the
`LogTag`/`ServiceType` name tables and per-tag field decoding
(`parse_log_fields()`). Both are live-verified against a real Supramatic E4 -
that check is also what caught a transcription error in `SERVICE_TYPE_NAMES`
(wire byte 17 is `ELEMENTS_COUNTER`, not `ENGINE_RUNTIME` - the
wire-byte-to-meaning mapping in the decompiled app is an explicit switch
statement, not the `ServiceType` enum's own declared integer values). A
handful of `ServiceType` entries carry a proprietary Hoermann fixed-32-day-
month timestamp encoding instead of a plain counter - NOT decoded here (see
`SERVICE_TYPE_IS_TIMESTAMP`), only the plain-integer counters (including
operating hours) are. See the CLI's `view-log` command for a ready-to-use
example.
