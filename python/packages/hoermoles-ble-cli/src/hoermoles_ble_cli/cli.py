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

  uv run hoermoles-ble menu-get --address F1:26:AF:CC:41:86 52
  uv run hoermoles-ble menu-set --address F1:26:AF:CC:41:86 52=1

  uv run hoermoles-ble view-log --address F1:26:AF:CC:41:86
"""

import argparse
import asyncio
import getpass
import sys
import time
from pathlib import Path

from hoermoles_ble import (
    GATE_ACTIONS,
    LOG_TAG_NAMES,
    PREFIX_ENCRYPTED,
    PREFIX_PLAIN,
    SERVICE_TYPE_IS_TIMESTAMP,
    SERVICE_TYPE_NAMES,
    BundleEntry,
    BundleError,
    Credentials,
    DeviceInfo,
    DriveMenuTable,
    HoermannClient,
    PropertiesRejected,
    RegistrationTimeout,
    bundle_to_json,
    decode_bundle,
    default_credentials_path,
    encode_bundle,
    find_qr_for_address,
    get_device_info,
    is_encrypted_bundle,
    known_qr_serial_map,
    list_device_infos,
    list_saved_credential_paths,
    log_timestamp_to_datetime,
    menu_setting_for_wire_group,
    menu_table_for_product,
    parse_log_fields,
    product_class_and_id_from_qr_prefix,
    save_device_info,
    save_qr,
    scan_devices,
    serial_no_from_qr_prefix,
    wire_group_for_menu_number,
)
from hoermoles_ble.advertisement import PRODUCT_TYPE_NAMES
from hoermoles_ble.ble_transport import BleakTransport
from hoermoles_ble.protocol import parse_qr_code


def log(msg: str) -> None:
    """Progress and diagnostics go to stderr, never stdout.

    Every command here keeps stdout for its actual result - scan findings, menu
    values, log entries, and above all `export --stdout`, whose whole point is
    to be copied or piped somewhere. Interleaving timestamped progress lines
    with that output made it unusable for exactly that:

        hoermoles-ble export --stdout | hoermoles-ble import -

    Both streams still appear in a terminal, so nothing is hidden from an
    interactive user.
    """
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


async def cmd_scan(args) -> None:
    known = known_qr_serial_map(config_dir=args.config_dir)

    log(f"Scanning for {args.timeout:.0f}s for Hoermann BlueSecur drives...")
    devices = await scan_devices(timeout=args.timeout, adapter=args.adapter)
    if not devices:
        print("No devices found.")
        return
    for info in devices:
        print(f"\n{info.address}  (RSSI {info.rssi} dBm)")
        if info.product_class is not None:
            device_info = DeviceInfo(
                info.address, info.product_class, info.product_id, info.product_name, info.serial_no
            )
            save_device_info(device_info, config_dir=args.config_dir)
        if info.product_name:
            print(f"  Product:                {info.product_name} (class={info.product_class}, id={info.product_id})")
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
        log(
            f"No --qr-file given, looking for a matching saved QR code for {args.address} "
            f"(scanning for up to {args.timeout:.0f}s)..."
        )
        qr_text = await find_qr_for_address(
            args.address, timeout=args.timeout, adapter=args.adapter, config_dir=args.config_dir
        )
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

    prefix, _ = parse_qr_code(qr_text)
    product_info = product_class_and_id_from_qr_prefix(prefix)
    if product_info is not None:
        product_class, product_id = product_info
        product_name = PRODUCT_TYPE_NAMES.get((product_class, product_id)) or PRODUCT_TYPE_NAMES.get(
            (product_class, None)
        )
        device_info = DeviceInfo(
            args.address, product_class, product_id, product_name, serial_no_from_qr_prefix(prefix)
        )
        devices_path = save_device_info(device_info, config_dir=args.config_dir)
        log(
            f"Product type: {product_name or 'unknown'} (class={product_class}, id={product_id}), "
            f"saved to {devices_path}"
        )
    else:
        log(
            "Could not determine the product type from the QR code prefix (non-version-3 layout?) - "
            "run 'scan' near the drive to detect it instead."
        )


def _load_credentials(args) -> Credentials:
    if args.key_file:
        return Credentials.load(args.key_file)
    if args.address:
        return Credentials.load_for_device(args.address, config_dir=args.config_dir)
    try:
        credentials = Credentials.load_first(config_dir=args.config_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    log(f"No --address given, using the only/first saved credentials: {credentials.device_address}")
    return credentials


async def cmd_exec(args) -> None:
    credentials = _load_credentials(args)
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


def _menu_group_or_exit(table: DriveMenuTable, menu_number: int) -> int:
    group = wire_group_for_menu_number(table.settings, menu_number)
    if group is None:
        raise SystemExit(
            f"Menu {menu_number} isn't in the {table.product_name} menu table (hoermoles_ble.menu_settings)."
        )
    return group


def _resolve_menu_table(args, credentials: Credentials) -> DriveMenuTable:
    """Figures out which hoermoles_ble.menu_settings.DriveMenuTable applies to this drive
    from the device registry (see 'scan'/'register'/list-devices - a plain 'scan' near the
    drive is enough, no credentials/pairing needed for that part)."""
    device_info = get_device_info(credentials.device_address, config_dir=args.config_dir)
    if device_info is None:
        raise SystemExit(
            f"No stored product type for {credentials.device_address} - run 'scan' near the "
            "drive first (that's all it takes, no re-registration needed), then retry."
        )
    table = menu_table_for_product(device_info.product_class, device_info.product_id)
    if table is None:
        raise SystemExit(
            f"No menu table known for {device_info.product_name or 'this product'} "
            f"(class={device_info.product_class}, id={device_info.product_id})."
        )
    return table


async def cmd_menu_get(args) -> None:
    credentials = _load_credentials(args)
    address = args.address or credentials.device_address
    table = _resolve_menu_table(args, credentials)
    menu_numbers = [int(n) for n in args.menu_numbers] or None
    menu_groups = [_menu_group_or_exit(table, n) for n in menu_numbers] if menu_numbers else None

    async with HoermannClient(BleakTransport(address, adapter=args.adapter, on_log=log), on_log=log) as client:
        log(f"Connected to {address}, waiting for the initial notification (challenge)...")
        try:
            await client.wait_for_any_notification(timeout=10.0)
        except asyncio.TimeoutError:
            log("WARNING: no initial notification, challenge may be stale")

        log(f"Reading properties from {table.product_name} (this can take a while for the full table)...")
        values = await client.read_properties(credentials, menu_groups=menu_groups, timeout=20.0)

    for menu_group, value in sorted(values.items()):
        setting = menu_setting_for_wire_group(table.settings, menu_group)
        if setting is None:
            print(f"[wire group {menu_group}, not in the {table.product_name} table] = {value}")
            continue
        parameter = next((p for p in setting.parameters if p.value == value), None)
        text = f" ({parameter.text})" if parameter else ""
        label = setting.label_en or setting.label
        print(f"menu {setting.menu_number:>3} {label}: {value}{text}")


async def cmd_menu_set(args) -> None:
    credentials = _load_credentials(args)
    address = args.address or credentials.device_address
    table = _resolve_menu_table(args, credentials)

    settings = {}
    for item in args.settings:
        menu_str, sep, value_str = item.partition("=")
        if not sep:
            raise SystemExit(f"Expected <menu_number>=<value>, got '{item}'")
        settings[_menu_group_or_exit(table, int(menu_str))] = int(value_str)

    async with HoermannClient(BleakTransport(address, adapter=args.adapter, on_log=log), on_log=log) as client:
        log(f"Connected to {address}, waiting for the initial notification (challenge)...")
        try:
            await client.wait_for_any_notification(timeout=10.0)
        except asyncio.TimeoutError:
            log("WARNING: no initial notification, challenge may be stale")

        log(f"Writing {len(settings)} setting(s) to {table.product_name}...")
        try:
            await client.write_properties(credentials, settings, timeout=20.0)
        except PropertiesRejected as exc:
            log(f"ERROR: {exc}")
            raise SystemExit(1)

    log("Done.")


async def cmd_list_devices(args) -> None:
    """Lists every drive we know the product type of (from 'scan' and/or 'register') -
    'registered' below means we also hold credentials for it (see 'register'), not just
    that we've seen its advertisement."""
    infos = list_device_infos(config_dir=args.config_dir)
    if not infos:
        print("No known drives yet - run 'scan' near a drive first.")
        return
    for info in infos:
        serial = f"  serial={info.serial_no}" if info.serial_no is not None else ""
        registered = (
            "registered"
            if default_credentials_path(info.device_address, args.config_dir).exists()
            else "not registered (no credentials)"
        )
        print(
            f"{info.device_address}  {info.product_name or '?'} "
            f"(class={info.product_class}, id={info.product_id}){serial}  [{registered}]"
        )


def _collect_bundle_entries(args) -> list[BundleEntry]:
    """The drives to export: one specific --address, or (default) every drive we
    hold credentials for. The non-secret product metadata from devices.json is
    attached where known, so the web app can pick the right menu table without
    needing a BLE scan of its own."""
    if args.address:
        paths = [default_credentials_path(args.address, args.config_dir)]
        if not paths[0].exists():
            raise SystemExit(f"No saved credentials for {args.address} ({paths[0]}).")
    else:
        paths = list_saved_credential_paths(args.config_dir)
        if not paths:
            raise SystemExit("No saved credentials to export - register a device first.")

    entries = []
    for path in paths:
        credentials = Credentials.load(path)
        device_info = get_device_info(credentials.device_address, config_dir=args.config_dir)
        entries.append(BundleEntry(credentials=credentials, device_info=device_info))
    return entries


def _ask_passphrase(confirm: bool) -> str:
    passphrase = getpass.getpass("Passphrase: ")
    if not passphrase:
        raise SystemExit("Empty passphrase - aborting.")
    if confirm and getpass.getpass("Repeat passphrase: ") != passphrase:
        raise SystemExit("Passphrases do not match - aborting.")
    return passphrase


def _print_qr(text: str) -> None:
    try:
        import segno
    except ImportError as exc:  # pragma: no cover - depends on the install extra
        raise SystemExit(
            "QR output needs the 'segno' package - install hoermoles-ble-cli with its "
            "default dependencies, or use --out/--stdout instead."
        ) from exc

    # error="l" (7% recovery): the code is shown on a clean screen and scanned
    # immediately, so spending modules on damage tolerance only makes it denser
    # and harder for a phone camera to resolve.
    qr = segno.make(text, error="l")
    qr.terminal(compact=True)
    print(f"\n({len(text)} characters, QR version {qr.version})")
    if qr.version >= 20:
        print(
            "This code is dense - if your camera struggles, export one drive at a time\n"
            "(--address) or use --out to write a JSON file instead."
        )


async def cmd_export(args) -> None:
    """Hand credentials to another client - above all the web app, which has no
    access to ~/.hoermoles. See hoermoles_ble.bundle for the wire format."""
    entries = _collect_bundle_entries(args)
    passphrase = _ask_passphrase(confirm=True) if args.encrypt else None

    if args.out:
        if passphrase is not None:
            raise SystemExit("--encrypt applies to the text/QR form only; the JSON file form is always plaintext.")
        target = Path(args.out)
        target.write_text(bundle_to_json(entries))
        target.chmod(0o600)
        log(f"Wrote {len(entries)} credential(s) to {target} - this file contains root keys, treat it accordingly.")
        return

    text = encode_bundle(entries, passphrase=passphrase)

    if args.stdout:
        print(text)
    else:
        _print_qr(text)

    log(f"{len(entries)} credential(s) encoded.")
    if passphrase is None:
        log(
            "WARNING: this is an UNENCRYPTED root key - anyone who photographs or "
            "copies it can operate the drive. Use --encrypt for anything that leaves "
            "this machine or gets shown on a shared screen."
        )


def _read_bundle_source(source: str) -> str:
    """Resolves the `import` argument, which may be '-' for stdin, a file path,
    or the bundle text itself.

    The text forms are checked *before* touching the filesystem on purpose: a
    bundle string is far longer than any filesystem's maximum filename, and on
    Python <= 3.11 `Path.exists()` raises OSError(ENAMETOOLONG) instead of
    returning False (3.12 widened the errnos it swallows). Probing the path
    first therefore crashed on exactly the input this command exists to accept.
    """
    if source == "-":
        return sys.stdin.read()

    stripped = source.strip()
    if stripped.startswith((PREFIX_PLAIN, PREFIX_ENCRYPTED, "{")) or "#import=" in stripped:
        return source

    try:
        path = Path(source)
        if path.exists():
            return path.read_text()
    except OSError:
        pass  # not a usable path - fall through and let decode_bundle judge it

    return source


async def cmd_import(args) -> None:
    """Read a bundle produced by 'export' or by the web app back into
    ~/.hoermoles - the reverse direction, so a drive registered on a phone
    becomes usable from the CLI and (later) Home Assistant."""
    text = _read_bundle_source(args.source)

    passphrase = _ask_passphrase(confirm=False) if is_encrypted_bundle(text) else None

    try:
        entries = decode_bundle(text, passphrase=passphrase)
    except BundleError as exc:
        raise SystemExit(str(exc)) from exc

    for entry in entries:
        address = entry.credentials.device_address
        target = default_credentials_path(address, args.config_dir)
        if target.exists() and not args.force:
            log(f"SKIP {address}: credentials already exist at {target} (use --force to overwrite)")
            continue
        saved_path = entry.credentials.save(config_dir=args.config_dir)
        log(f"Imported {address} (RootID={entry.credentials.root_id}) to {saved_path}")
        if entry.device_info is not None:
            save_device_info(entry.device_info, config_dir=args.config_dir)
            log(f"  Product type: {entry.device_info.product_name or 'unknown'}")


async def cmd_view_log(args) -> None:
    credentials = _load_credentials(args)
    address = args.address or credentials.device_address

    async with HoermannClient(BleakTransport(address, adapter=args.adapter, on_log=log), on_log=log) as client:
        log(f"Connected to {address}, waiting for the initial notification (challenge)...")
        try:
            await client.wait_for_any_notification(timeout=10.0)
        except asyncio.TimeoutError:
            log("WARNING: no initial notification, challenge may be stale")

        log("Reading service/diagnostics counters...")
        service_data = await client.read_service_data(credentials, timeout=20.0)

        log("Reading audit log...")
        log_entries = await client.read_log(credentials, timeout=20.0)

    print("\n=== Service/diagnostics counters ===")
    if not service_data:
        print("(none)")
    for service_type, value in sorted(service_data.items()):
        name = SERVICE_TYPE_NAMES.get(service_type, f"unknown service type {service_type}")
        if value == 0xFFFFFFFF:
            print(f"{name}: undefined")
        elif service_type in SERVICE_TYPE_IS_TIMESTAMP:
            print(f"{name}: raw={value} (proprietary Hoermann timestamp encoding, not decoded)")
        else:
            print(f"{name}: {value}")

    print("\n=== Audit log ===")
    if not log_entries:
        print("(none)")
    for log_tag, timestamp_raw, data in log_entries:
        tag_name = LOG_TAG_NAMES.get(log_tag, f"unknown log tag {log_tag}")
        timestamp = log_timestamp_to_datetime(timestamp_raw)
        fields = parse_log_fields(log_tag, data)
        fields_str = ", ".join(f"{key}={value}" for key, value in fields.items())
        suffix = f"  ({fields_str})" if fields_str else ""
        print(f"{timestamp:%Y-%m-%d %H:%M:%S}  {tag_name}{suffix}")


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Wider than argparse's default so the example invocations in the
    subcommand list (see `help=` below) don't get truncated."""

    def __init__(self, prog):
        super().__init__(prog, max_help_position=52, width=100)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=_HelpFormatter)
    ap.add_argument("--adapter", default=None, help="BlueZ adapter, e.g. hci1. Default: system default.")
    ap.add_argument(
        "--config-dir",
        default=None,
        help="Base directory for credentials. Priority: --config-dir > $HOERMOLES_CONF_DIR > .env > ~/.hoermoles",
    )
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    p_scan = sub.add_parser(
        "scan",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble scan",
        description="Scan for Hoermann BlueSecur drives (no key needed).",
    )
    p_scan.add_argument("--timeout", type=float, default=8.0, help="Scan duration in seconds (default: 8)")
    p_scan.set_defaults(func=cmd_scan)

    p_qr = sub.add_parser(
        "save-qr",
        formatter_class=_HelpFormatter,
        help='uv run hoermoles-ble save-qr "<QR code content>"',
        description="Remember a QR code's content (for 'register'/'scan' without --qr-file).",
    )
    p_qr.add_argument("content", help="Full QR code content as text")
    p_qr.set_defaults(func=cmd_save_qr)

    p_reg = sub.add_parser(
        "register",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble register --address <MAC>",
        description="Perform the one-time QR code registration.",
    )
    p_reg.add_argument("--address", required=True, help="BLE MAC address of the drive")
    p_reg.add_argument(
        "--qr-file",
        default=None,
        help="Text file containing the QR code content. Default: look up a matching "
        "saved QR code via scan (see save-qr)",
    )
    p_reg.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Scan duration in seconds to find the matching QR code, only relevant without --qr-file (default: 8)",
    )
    p_reg.add_argument(
        "--key-file",
        default=None,
        help="Target file for the credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json",
    )
    p_reg.set_defaults(func=cmd_register)

    p_exec = sub.add_parser(
        "exec",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble exec --address <MAC> open|close|impulse|light|partial|ventilation",
        description="Trigger a named gate action (open, close, impulse, light, partial, ventilation).",
    )
    p_exec.add_argument(
        "--address",
        default=None,
        help="BLE MAC address (also used to find the credentials file). Default: the only/first saved credentials",
    )
    p_exec.add_argument(
        "--key-file",
        default=None,
        help="File with saved credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json",
    )
    p_exec.add_argument(
        "action",
        choices=list(GATE_ACTIONS),
        metavar="action",
        help="One of: " + ", ".join(GATE_ACTIONS) + ". 'impulse' is the "
        "factory-default toggle (open/stop/close); 'open'/'close' are direct "
        "direction commands; 'light', 'partial' and 'ventilation' depend on "
        "the device's configuration.",
    )
    p_exec.set_defaults(func=cmd_exec)

    p_menu_get = sub.add_parser(
        "menu-get",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble menu-get --address <MAC> [menu_number ...]",
        description="Read operator menu/parameter settings - see hoermoles_ble.menu_settings for the "
        "known products (Supramatic E4 read-verified against real hardware; others are "
        "structurally derived, not yet verified). Without menu numbers, reads the entire "
        "table. Needs the product type in the device registry - run 'scan' near the drive "
        "first if 'list-devices' doesn't show it yet.",
    )
    p_menu_get.add_argument(
        "--address",
        default=None,
        help="BLE MAC address (also used to find the credentials file). Default: the only/first saved credentials",
    )
    p_menu_get.add_argument(
        "--key-file",
        default=None,
        help="File with saved credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json",
    )
    p_menu_get.add_argument(
        "menu_numbers",
        nargs="*",
        metavar="menu_number",
        help="Menu number(s) to read (e.g. 25 52). Default: all known menus.",
    )
    p_menu_get.set_defaults(func=cmd_menu_get)

    p_menu_set = sub.add_parser(
        "menu-set",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble menu-set --address <MAC> 25=1 52=0",
        description="Write operator menu/parameter settings - see hoermoles_ble.menu_settings for the "
        "known products. Needs the product type in the device registry - run 'scan' near "
        "the drive first if 'list-devices' doesn't show it yet. NOT YET VERIFIED against "
        "real hardware for any product - read the current value first and double check "
        "against the printed manual.",
    )
    p_menu_set.add_argument(
        "--address",
        default=None,
        help="BLE MAC address (also used to find the credentials file). Default: the only/first saved credentials",
    )
    p_menu_set.add_argument(
        "--key-file",
        default=None,
        help="File with saved credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json",
    )
    p_menu_set.add_argument(
        "settings",
        nargs="+",
        metavar="menu_number=value",
        help="One or more <menu_number>=<value> pairs, e.g. 25=1 52=0",
    )
    p_menu_set.set_defaults(func=cmd_menu_set)

    p_list_devices = sub.add_parser(
        "list-devices",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble list-devices",
        description="List every drive whose product type we know (from 'scan' and/or 'register') "
        "and whether we also hold credentials for it ('registered').",
    )
    p_list_devices.set_defaults(func=cmd_list_devices)

    p_export = sub.add_parser(
        "export",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble export [--address <MAC>] [--encrypt|--out FILE]",
        description="Export saved credentials as a transportable bundle, so another client "
        "- above all the web app, which cannot read ~/.hoermoles - can use them. "
        "Default output is a QR code in the terminal; --out writes a JSON file "
        "instead. A root key is a physical door key: prefer --encrypt for "
        "anything that leaves this machine.",
    )
    p_export.add_argument(
        "--address",
        default=None,
        help="Only export this drive. Default: every drive with saved credentials.",
    )
    p_export.add_argument(
        "--encrypt",
        action="store_true",
        help="Protect the text/QR form with a passphrase (AES-256-GCM, PBKDF2-SHA256). Prompts for it.",
    )
    output_group = p_export.add_mutually_exclusive_group()
    output_group.add_argument("--out", default=None, help="Write a JSON bundle file instead of printing a QR code")
    output_group.add_argument(
        "--stdout",
        action="store_true",
        help="Print the bundle text (HMOLES1:...) instead of a QR code - for piping/copying",
    )
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser(
        "import",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble import <file|text|->",
        description="Import a credential bundle produced by 'export' or by the web app into "
        "the local config dir. Accepts a file path, the bundle text itself, a "
        "full '#import=...' URL, or '-' to read stdin. Prompts for the "
        "passphrase if the bundle is encrypted.",
    )
    p_import.add_argument("source", help="Bundle file path, bundle text, import URL, or '-' for stdin")
    p_import.add_argument(
        "--force",
        action="store_true",
        help="Overwrite credentials that already exist for a device (default: skip them)",
    )
    p_import.set_defaults(func=cmd_import)

    p_view_log = sub.add_parser(
        "view-log",
        formatter_class=_HelpFormatter,
        help="uv run hoermoles-ble view-log --address <MAC>",
        description="Read the drive's security/access audit log (admin/user actions, "
        "blocked attempts, clock changes) and service/diagnostics counters "
        "(operating hours, door cycles, ...) - see hoermoles_ble.device_log. "
        "Live-verified against a real Supramatic E4.",
    )
    p_view_log.add_argument(
        "--address",
        default=None,
        help="BLE MAC address (also used to find the credentials file). Default: the only/first saved credentials",
    )
    p_view_log.add_argument(
        "--key-file",
        default=None,
        help="File with saved credentials (JSON). Default: ~/.hoermoles/credentials/<address>.json",
    )
    p_view_log.set_defaults(func=cmd_view_log)

    args = ap.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
