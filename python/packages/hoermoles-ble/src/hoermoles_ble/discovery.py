"""BLE scan for Hoermann BlueSecur drives - returns AdvertisementInfo objects, with no
connection or root key needed (see advertisement.py)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Union

from bleak import BleakScanner

from .advertisement import COMPANY_ID, AdvertisementInfo
from .protocol import BC_SERVICE
from .qr_store import known_qr_serial_map


async def scan_devices(timeout: float = 8.0, adapter: Optional[str] = None) -> list[AdvertisementInfo]:
    """Scans for `timeout` seconds for devices advertising the BlueConnect
    service (669a9001-...), collecting all manufacturer-data payloads seen
    (Company ID 1972) for each device found - a single advertisement packet
    usually isn't enough for the full parser (see advertisement.py), so the
    scan runs over an entire time window."""
    payloads_by_address: dict[str, list[bytes]] = {}
    rssi_by_address: dict[str, int] = {}

    def _on_detection(device, adv_data) -> None:
        if BC_SERVICE.lower() not in [u.lower() for u in adv_data.service_uuids]:
            return
        rssi_by_address[device.address] = adv_data.rssi
        payload = adv_data.manufacturer_data.get(COMPANY_ID)
        if payload:
            seen = payloads_by_address.setdefault(device.address, [])
            if payload not in seen:
                seen.append(payload)
        else:
            payloads_by_address.setdefault(device.address, [])

    scanner = BleakScanner(detection_callback=_on_detection, adapter=adapter)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    return [
        AdvertisementInfo.from_scan(address, rssi_by_address[address], payloads)
        for address, payloads in payloads_by_address.items()
    ]


async def find_qr_for_address(
    address: str,
    timeout: float = 8.0,
    adapter: Optional[str] = None,
    config_dir: Optional[Union[str, Path]] = None,
) -> Optional[str]:
    """Scans for `address` and, if the serial number decoded from it
    (AdvertisementInfo.serial_no) matches one of the saved QR codes (see
    qr_store.known_qr_serial_map), returns that QR code's content. None if the
    device wasn't found, its serial number wasn't decodable, or no saved QR
    code matches."""
    known = known_qr_serial_map(config_dir)
    if not known:
        return None
    devices = await scan_devices(timeout=timeout, adapter=adapter)
    for info in devices:
        if info.address.lower() == address.lower() and info.serial_no is not None:
            return known.get(info.serial_no)
    return None
