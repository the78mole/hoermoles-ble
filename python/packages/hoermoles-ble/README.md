# hoermoles-ble

Protocol core (`protocol.py`, `crypto_rsa.py`) and BLE client (`client.py`,
`transport.py`, `ble_transport.py`) for the Hoermann BlueSecur "Signed"
channel.

`protocol.py` deliberately has no third-party dependencies (stdlib only) and
serves as a template for ports to other languages. `bleak` (for the real BLE
transport) is an optional extra: `pip install hoermoles-ble[bleak]`.

For details on where the protocol comes from, see `reveng/ANALYSIS.md` in the
project root.
