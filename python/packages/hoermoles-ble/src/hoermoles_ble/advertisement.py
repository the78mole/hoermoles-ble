"""
Passive parsing of the Hoermann BlueSecur BLE advertisement (Manufacturer Specific Data,
Company ID 0x07B4 = 1972) - provides status info WITHOUT a connection and
WITHOUT a root key.

Reconstructed from SAL.BlueConnect.API.Devices.Info.DeviceData (BLEAdvertisementData.cs,
BlueSecurAdvertisementService.cs, ServiceProduct.cs, product-specific *AdvertisementService.cs)
and verified empirically against a real, freshly reset drive: after a reset via
menu 19/parameter 02, `admins_can_be_teached` reliably flipped from False to
True - confirming the bit position. See reveng/ANALYSIS.md section 8.3.

Important quirk: the device sends the content for Company ID 1972 across two
different, alternating manufacturer-data packets (6 and 17 bytes on our test
device). Only the 2-byte company ID + both payloads concatenated (shortest
first) yields the byte sequence expected by the original parser -
`combine_manufacturer_payloads()` reproduces that. A single scan callback
usually only sees one of the two packets; `scan_devices()` in discovery.py
therefore collects over the entire scan window.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

COMPANY_ID = 1972  # 0x07B4

# SAL.BlueConnect.API.Devices.Info.DeviceData.DeviceService.ProductType, incomplete
# (only the mappings visible in the decompiled BLEAdvertisementData.cs)
PRODUCT_TYPE_NAMES = {
    (1, None): "HET",
    (2, 1): "Supramatic Serie 4",
    (2, 2): "Supramatic Serie 4",
    (2, 17): "Rollmatic 2",
    (2, 33): "SilentDrive 2",
    (2, 49): "Supramatic 4 H4",
    (3, 1): "ST560", (3, 2): "ST560", (3, 8): "ST560", (3, 40): "ST560",
    (3, 17): "ST560 Dockleveller",
    (3, 33): "ST545",
}


def _bit(b: int, position: int) -> bool:
    """DeviceData.GetBitFromByte: position is 1-indexed (1 = LSB)."""
    return (b & (1 << (position - 1))) != 0


def combine_manufacturer_payloads(payloads: list[bytes]) -> bytes:
    """2-byte company ID (LE) + the payloads seen, shortest first - see module
    docstring. With only one payload seen, only that one is used; the length
    then usually isn't enough for the full parser (>=17 bytes needed, see
    AdvertisementInfo.parse_error)."""
    ordered = sorted(set(payloads), key=len)
    return COMPANY_ID.to_bytes(2, "little") + b"".join(ordered)


@dataclass
class AdvertisementInfo:
    """Everything that can be read purely from the advertisement without a
    root key. Fields stay None if not enough raw data was seen, or the field
    isn't defined for the given product type (see parse_error)."""

    address: str
    rssi: int
    raw_manufacturer_data: list[str]  # hex strings, as seen during the scan

    product_class: Optional[int] = None
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    serial_no: Optional[int] = None
    is_blue_secur: Optional[bool] = None
    clock_time_set: Optional[bool] = None
    protection_active: Optional[bool] = None
    admin_teached: Optional[bool] = None
    admins_can_be_teached: Optional[bool] = None

    in_action: Optional[bool] = None
    opening_time: Optional[bool] = None
    warning_time: Optional[bool] = None
    emergency_mode: Optional[bool] = None
    low_battery: Optional[bool] = None
    teached_control: Optional[bool] = None
    vacation_mode: Optional[bool] = None

    relais1_open: Optional[bool] = None
    relais2_open: Optional[bool] = None
    opening_progress_percent: Optional[float] = None
    maintenance_required: Optional[bool] = None

    parse_error: Optional[str] = None

    @classmethod
    def from_scan(cls, address: str, rssi: int, payloads: list[bytes]) -> "AdvertisementInfo":
        info = cls(address=address, rssi=rssi, raw_manufacturer_data=[p.hex() for p in payloads])
        if not payloads:
            return info
        distinct = list({p for p in payloads})
        if len(distinct) < 2:
            # Empirically (see module docstring) the device sends status/product
            # info in two alternating packets - with only one of them the length
            # and "enough bytes present" checks would pass, but the result would
            # be computed from the wrong bytes (e.g. all flags falsely False).
            # Better to honestly parse nothing than to fake a wrong result.
            info.parse_error = (f"only {len(distinct)} distinct manufacturer-data packet(s) "
                                 "seen, need at least 2 for full parsing - "
                                 "scan longer (increase --timeout)")
            return info
        try:
            info._parse(combine_manufacturer_payloads(distinct))
        except Exception as exc:  # advertisement parsing must never crash a scan
            info.parse_error = f"{type(exc).__name__}: {exc}"
        return info

    def _parse(self, data: bytes) -> None:
        # BLEAdvertisementData.ParseData
        if len(data) < 4:
            self.parse_error = "not enough raw data for product class/ID"
            return
        product_id, product_class = data[2], data[3]
        self.product_class = product_class
        self.product_id = product_id
        self.product_name = (PRODUCT_TYPE_NAMES.get((product_class, product_id))
                              or PRODUCT_TYPE_NAMES.get((product_class, None)))

        if len(data) < 17:
            self.parse_error = (f"only {len(data)} of the required >=17 bytes seen "
                                 "(maybe not both advertisement packets were captured during the scan)")
            return

        status_byte = data[4]
        self.is_blue_secur = _bit(status_byte, 1)
        self.clock_time_set = _bit(status_byte, 3)
        self.admin_teached = _bit(status_byte, 4)
        self.protection_active = _bit(status_byte, 5)
        self.admins_can_be_teached = _bit(status_byte, 6)
        self.in_action = _bit(status_byte, 7)
        self.opening_time = _bit(status_byte, 8)

        # BlueSecurAdvertisementService/ServiceProduct receive the same 13 bytes from here on
        product_data = data[4:17]
        if len(product_data) >= 2:
            b1 = product_data[1]
            self.warning_time = _bit(b1, 1)
            self.emergency_mode = _bit(b1, 2)
            self.low_battery = _bit(b1, 3)
            self.teached_control = not _bit(b1, 7)
            self.vacation_mode = _bit(b1, 8)

        if product_class == 1 and len(product_data) >= 1:
            # HetBlueSecurAdvertisementService.ParseData replaces the ServiceProduct base fields entirely
            self.relais1_open = _bit(product_data[0], 1)
            self.relais2_open = _bit(product_data[0], 2)
        elif product_class == 2 and len(product_data) >= 7:
            # SupramaticBlueSecurAdvertisementService.ParseDeviceDependentData
            self.opening_progress_percent = product_data[5] / 2.0
            self.maintenance_required = _bit(product_data[6], 1)

        # BLEAdvertisementData.ParseData: the serial number follows as a uint64 LE
        # from position 17 (4+13) onward - verified live against the QR code prefix
        # of the same device (see protocol.serial_no_from_qr_prefix / reveng/ANALYSIS.md).
        if len(data) >= 25:
            self.serial_no = struct.unpack_from("<Q", data, 17)[0]
