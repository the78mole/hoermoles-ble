#!/usr/bin/env python3
"""
Thin CLI wrapper around the hoermoles-ble library (package hoermoles_ble).
All protocol/crypto logic lives entirely in the library - this script only
handles argument parsing and I/O.

Without --key-file, credentials are stored under <config-dir>/credentials/<address>.json
and loaded from there. config-dir is resolved in this order:
1. --config-dir  2. environment variable HOERMOLES_CONF_DIR  3. HOERMOLES_CONF_DIR
from a .env file  4. default ~/.hoermoles (see hoermoles_ble/config.py).

Until there is an app with camera QR scanning, QR code contents can be
collected manually (e.g. photographed/typed off, one QR code per save-qr call).
'register' and 'scan' match them to the right device automatically via the
serial number shared between the QR code and the BLE advertisement:
  uv run hoermoles-ble save-qr "<QR code content>"

Examples (after `uv sync` in the workspace root python/):
  uv run hoermoles-ble scan

  uv run hoermoles-ble register --address F1:26:AF:CC:41:86

  uv run hoermoles-ble exec --address F1:26:AF:CC:41:86 open
"""
import argparse
import asyncio
import time

from hoermoles_ble import (
    Credentials,
    HoermannClient,
    RegistrationTimeout,
    GATE_ACTIONS,
    scan_devices,
    find_qr_for_address,
    save_qr,
    known_qr_serial_map,
)
from hoermoles_ble.ble_transport import BleakTransport


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


async def cmd_scan(args) -> None:
    known = known_qr_serial_map(config_dir=args.config_dir)

    log(f"Scanning for {args.timeout:.0f}s for Hoermann BlueSecur drives...")
    devices = await scan_devices(timeout=args.timeout, adapter=args.adapter)
    if not devices:
        print("No devices found.")
        return
    for info in devices:
        print(f"\n{info.address}  (RSSI {info.rssi} dBm)")
        if info.product_name:
            print(f"  Product:                {info.product_name} "
                  f"(class={info.product_class}, id={info.product_id})")
        if info.serial_no is not None:
            qr_status = "yes" if info.serial_no in known else f"no (0 of {len(known)} known QR codes match)"
            print(f"  QR code known:          {qr_status}")
        if info.admin_teached is not None:
            print(f"  Admin taught:           {info.admin_teached}")
            print(f"  New registration ok:    {info.admins_can_be_teached}")
            print(f"  Protection active:      {info.protection_active}")
            print(f"  Clock set:              {info.clock_time_set}")
            print(f"  In motion:              {info.in_action}")
            print(f"  Warning time running:   {info.warning_time}")
            print(f"  Emergency mode (batt.): {info.emergency_mode}")
            print(f"  Battery low:            {info.low_battery}")
            print(f"  Vacation mode:          {info.vacation_mode}")
            if info.relais1_open is not None:
                print(f"  Relay 1 open:           {info.relais1_open}")
                print(f"  Relay 2 open:           {info.relais2_open}")
            if info.opening_progress_percent is not None:
                print(f"  Opening progress:       {info.opening_progress_percent:.0f}%")
                print(f"  Maintenance due:        {info.maintenance_required}")
        if info.parse_error:
            print(f"  (incompletely parsed: {info.parse_error})")
        print(f"  Raw data (Manufacturer Data 1972): {info.raw_manufacturer_data}")


async def cmd_save_qr(args) -> None:
    saved_path = save_qr(args.content, config_dir=args.config_dir)
    log(f"QR code saved to {saved_path}")


async def cmd_register(args) -> None:
    if args.qr_file:
        with open(args.qr_file, "r") as f:
            qr_text = f.read()
    else:
        log(f"No --qr-file given, looking for a matching saved QR code for {args.address} "
            f"(scanning for up to {args.timeout:.0f}s)...")
        qr_text = await find_qr_for_address(args.address, timeout=args.timeout, adapter=args.adapter,
                                             config_dir=args.config_dir)
        if qr_text is None:
            raise SystemExit(
                f"No saved QR code matches {args.address} (or the device wasn't found) - "
                "run 'save-qr' first or pass --qr-file."
            )

    async with HoermannClient(BleakTransport(args.address, adapter=args.adapter, on_log=log), on_log=log) as client:
        log(f"Connected to {args.address}, waiting for the first notification...")
        try:
            await client.wait_for_any_notification(timeout=10.0)
        except asyncio.TimeoutError:
            log("WARNING: no initial notification received, continuing anyway")

        log("Sending registration (SET_REGISTER_KEY)...")
        try:
            credentials = await client.register(qr_text, args.address)
        except RegistrationTimeout as exc:
            log(f"ERROR: {exc}")
            raise SystemExit(1)

    log(f"RootID = {credentials.root_id}")
    log(f"Root key = {credentials.root_key.hex()}")
    saved_path = credentials.save(args.key_file, config_dir=args.config_dir)
    log(f"Saved to {saved_path}")


async def cmd_exec(args) -> None:
    if args.key_file:
        credentials = Credentials.load(args.key_file)
    elif args.address:
        credentials = Credentials.load_for_device(args.address, config_dir=args.config_dir)
    else:
        raise SystemExit("Provide either --key-file or --address.")
    address = args.address or credentials.device_address
    channel = GATE_ACTIONS[args.action]

    async with HoermannClient(BleakTransport(address, adapter=args.adapter, on_log=log), on_log=log) as client:
        log(f"Connected to {address}, waiting for the initial notification (challenge)...")
        try:
            await client.wait_for_any_notification(timeout=10.0)
        except asyncio.TimeoutError:
            log("WARNING: no initial notification, challenge may be stale")

        log(f"Sending '{args.action}' (CHANNEL_{channel}, RootID={credentials.root_id})...")
        await client.open_channel(credentials, channel=channel)

        log("Waiting for a response/status notification...")
        try:
            await client.wait_for_any_notification(timeout=5.0)
        except asyncio.TimeoutError:
            pass

    log("Done.")


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Wider than argparse's default so the example invocations in the
    subcommand list (see `help=` below) don't get truncated."""

    def __init__(self, prog):
        super().__init__(prog, max_help_position=52, width=100)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=_HelpFormatter)
    ap.add_argument("--adapter", default=None,
                     help="BlueZ adapter, e.g. hci1. Default: system default.")
    ap.add_argument("--config-dir", default=None,
                     help="Base directory for credentials. Priority: "
                          "--config-dir > $HOERMOLES_CONF_DIR > .env > ~/.hoermoles")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    p_scan = sub.add_parser(
        "scan", formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble scan",
        description="Scan for Hoermann BlueSecur drives (no key needed).")
    p_scan.add_argument("--timeout", type=float, default=8.0, help="Scan duration in seconds (default: 8)")
    p_scan.set_defaults(func=cmd_scan)

    p_qr = sub.add_parser(
        "save-qr", formatter_class=_HelpFormatter,
        help='uv run hoermoles-ble save-qr "<QR code content>"',
        description="Remember a QR code's content (for 'register'/'scan' without --qr-file).")
    p_qr.add_argument("content", help="Full QR code content as text")
    p_qr.set_defaults(func=cmd_save_qr)

    p_reg = sub.add_parser(
        "register", formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble register --address <MAC>",
        description="Perform the one-time QR code registration.")
    p_reg.add_argument("--address", required=True, help="BLE MAC address of the drive")
    p_reg.add_argument("--qr-file", default=None,
                        help="Text file containing the QR code content. Default: look up a matching "
                             "saved QR code via scan (see save-qr)")
    p_reg.add_argument("--timeout", type=float, default=8.0,
                        help="Scan duration in seconds to find the matching QR code, "
                             "only relevant without --qr-file (default: 8)")
    p_reg.add_argument("--key-file", default=None,
                        help="Target file for the credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json")
    p_reg.set_defaults(func=cmd_register)

    p_exec = sub.add_parser(
        "exec", formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble exec --address <MAC> open|close|impulse|light|partial|ventilation",
        description="Trigger a named gate action (open, close, impulse, light, partial, ventilation).")
    p_exec.add_argument("--address", default=None, help="BLE MAC address (also used to find the default credentials file)")
    p_exec.add_argument("--key-file", default=None,
                         help="File with saved credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json")
    p_exec.add_argument("action", choices=list(GATE_ACTIONS), metavar="action",
                         help="One of: " + ", ".join(GATE_ACTIONS) + ". 'impulse' is the "
                              "factory-default toggle (open/stop/close); 'open'/'close' are direct "
                              "direction commands; 'light', 'partial' and 'ventilation' depend on "
                              "the device's configuration.")
    p_exec.set_defaults(func=cmd_exec)

    args = ap.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
