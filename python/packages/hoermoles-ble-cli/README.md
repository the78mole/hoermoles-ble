# hoermoles-ble-cli

Thin CLI wrapper around `hoermoles-ble`. Install standalone with
`uv tool install hoermoles-ble-cli` (gives you the `hoermoles-ble` command
directly), or, from a workspace checkout, `uv sync` in the workspace root and
prefix every command below with `uv run`:

```
hoermoles-ble scan
hoermoles-ble list-devices                         # show known drives + product type
hoermoles-ble register --address <MAC> --qr-file <path-to-qr-code.txt>
hoermoles-ble exec --address <MAC> open
hoermoles-ble menu-get --address <MAC> 52          # read one operator menu
hoermoles-ble menu-set --address <MAC> 52=1        # write one operator menu
hoermoles-ble view-log --address <MAC>             # audit log + diagnostics counters
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
