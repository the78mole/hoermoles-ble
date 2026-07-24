"""
Registry of known (taught/registered) drives: which product each saved
credentials file belongs to (product_class/product_id, plus a human-readable
product_name and, if known, the serial number) - so callers like the CLI's
menu-get/menu-set can pick the right hoermoles_ble.menu_settings table
without asking the user every time.

Deliberately a separate file from credentials.py/Credentials: this is
non-secret metadata (no root key), and keeping it separate means credentials
stay exactly "the three values needed to trigger channels" (see
credentials.py) while this registry can list every known drive at once - a
single JSON file `<config_dir>/devices.json`, keyed by MAC address, is the
"overarching config that lists all known drives" a Credentials-per-file
layout can't give you on its own.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import resolve_config_dir


def default_devices_registry_path(config_dir: str | Path | None = None) -> Path:
    return resolve_config_dir(config_dir) / "devices.json"


@dataclass
class DeviceInfo:
    device_address: str
    product_class: int
    product_id: int
    product_name: str | None = None
    serial_no: int | None = None
    updated_unix: int = 0


def load_device_registry(config_dir: str | Path | None = None) -> dict[str, DeviceInfo]:
    """All known drives, keyed by MAC address (uppercase, colon form). Empty
    dict if nothing has been saved yet."""
    target = default_devices_registry_path(config_dir)
    if not target.exists():
        return {}
    raw = json.loads(target.read_text())
    return {
        address: DeviceInfo(
            device_address=address,
            product_class=entry["product_class"],
            product_id=entry["product_id"],
            product_name=entry.get("product_name"),
            serial_no=entry.get("serial_no"),
            updated_unix=entry.get("updated_unix", 0),
        )
        for address, entry in raw.items()
    }


def list_device_infos(config_dir: str | Path | None = None) -> list[DeviceInfo]:
    """All known drives, sorted by MAC address."""
    return [info for _, info in sorted(load_device_registry(config_dir).items())]


def get_device_info(device_address: str, config_dir: str | Path | None = None) -> DeviceInfo | None:
    return load_device_registry(config_dir).get(device_address.upper())


def save_device_info(info: DeviceInfo, config_dir: str | Path | None = None) -> Path:
    """Adds/updates one entry in the registry (read-modify-write of the whole
    file - fine for the expected handful of paired drives). Returns the path
    used."""
    registry = load_device_registry(config_dir)
    info.device_address = info.device_address.upper()
    info.updated_unix = info.updated_unix or int(time.time())
    registry[info.device_address] = info

    target = default_devices_registry_path(config_dir)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {address: asdict(entry) for address, entry in registry.items()}
    for entry in payload.values():
        del entry["device_address"]  # redundant - it's already the dict key
    target.write_text(json.dumps(payload, indent=2))
    return target
