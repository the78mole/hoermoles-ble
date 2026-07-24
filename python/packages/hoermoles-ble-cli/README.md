# hoermoles-ble-cli

Thin CLI wrapper around `hoermoles-ble`. After `uv sync` in the workspace root:

```
uv run hoermoles-ble scan
uv run hoermoles-ble list-devices                         # show known drives + product type
uv run hoermoles-ble register --address <MAC> --qr-file <path-to-qr-code.txt>
uv run hoermoles-ble exec --address <MAC> open
uv run hoermoles-ble menu-get --address <MAC> 52          # read one operator menu
uv run hoermoles-ble menu-set --address <MAC> 52=1        # write one operator menu
uv run hoermoles-ble view-log --address <MAC>             # audit log + diagnostics counters
```

`scan` (and `register`, via the QR code) saves each drive's product type to a
device registry (`<config-dir>/devices.json` - see `hoermoles_ble.devices`);
`menu-get`/`menu-set` use that to pick the right menu table automatically
(see `hoermoles_ble.menu_settings` for the known products - run `scan` near
the drive first if `list-devices` doesn't show it yet). Without menu
numbers, `menu-get` reads the entire table.

`view-log` shows the drive's security/access audit log (who registered,
channel toggles, blocked login attempts, ...) and service/diagnostics
counters (operating hours, door cycles, ...) - see `hoermoles_ble.device_log`.
