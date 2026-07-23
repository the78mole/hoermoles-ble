# hoermoles-ble-cli

Thin CLI wrapper around `hoermoles-ble`. After `uv sync` in the workspace root:

```
uv run hoermoles-ble scan
uv run hoermoles-ble register --address <MAC> --qr-file <path-to-qr-code.txt>
uv run hoermoles-ble exec --address <MAC> open
```
