"""
Passive parsing of the Hoermann BlueSecur BLE advertisement (Manufacturer Specific Data,
Company ID 0x07B4 = 1972) - provides status info WITHOUT a connection and
WITHOUT a root key.

Reconstructed from SAL.BlueConnect.API.Devices.Info.DeviceData (BLEAdvertisementData.cs,
BlueSecurAdvertisementService.cs, ServiceProduct.cs, product-specific *AdvertisementService.cs)
and verified empirically against a real, freshly reset drive: after a reset via
menu 19/parameter 02, `admins_can_be_teached` reliably flipped from False to
True - confirming the bit position.

Important quirk: the device sends the content for Company ID 1972 across two
different, alternating manufacturer-data packets (6 and 17 bytes on our test
device). Only the 2-byte company ID + both payloads concatenated (shortest
first) yields the byte sequence expected by the original parser -
`combine_manufacturer_payloads()` reproduces that. `scan_devices()` in
discovery.py therefore collects over the entire scan window.

An *idle* drive, however, was observed emitting ONLY the long (17-byte) packet -
byte-identical, for minutes on end (a 5-minute idle capture never once saw the
short packet); the short "status" packet shows up mainly around activity. So
"scan longer" does not help at rest. The long packet alone still carries the
serial number and - for product_class 2 - the opening position and maintenance
flag, so `from_scan()` does a partial parse of it (see `_parse_long_packet_only`
and LONG_PACKET_MIN_LEN); the status flags stay None until the short packet is
seen.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

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
    (3, 1): "ST560",
    (3, 2): "ST560",
    (3, 8): "ST560",
    (3, 40): "ST560",
    (3, 17): "ST560 Dockleveller",
    (3, 33): "ST545",
}


# The BlueSecur advertisement is split across a short and a long manufacturer
# packet (see the module docstring). On every device verified so far (Supramatic
# S4, product_class 2) the long packet is 17 bytes: it carries product_data[4:]
# plus the 8-byte serial number, while the short (6-byte) packet carries
# product_id/class, the status byte and product_data[0:4]. An *idle* drive was
# observed emitting ONLY the long packet for minutes at a time (the short packet
# appears mainly around activity), so this is the minimum length at which a lone
# packet can still yield the serial and - for product_class 2 - the position.
LONG_PACKET_MIN_LEN = 17


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

    product_class: int | None = None
    product_id: int | None = None
    product_name: str | None = None
    serial_no: int | None = None
    is_blue_secur: bool | None = None
    clock_time_set: bool | None = None
    protection_active: bool | None = None
    admin_teached: bool | None = None
    admins_can_be_teached: bool | None = None

    in_action: bool | None = None
    opening_time: bool | None = None
    warning_time: bool | None = None
    emergency_mode: bool | None = None
    low_battery: bool | None = None
    teached_control: bool | None = None
    vacation_mode: bool | None = None

    relais1_open: bool | None = None
    relais2_open: bool | None = None
    opening_progress_percent: float | None = None
    maintenance_required: bool | None = None

    parse_error: str | None = None

    @classmethod
    def from_scan(
        cls, address: str, rssi: int, payloads: list[bytes], product_class: int | None = None
    ) -> AdvertisementInfo:
        """Parse whatever was captured. With both advertisement packets a full
        parse runs (product info + status flags + position + serial). With only
        one packet - the common case for an *idle* drive, which keeps sending just
        its long packet (see module docstring / LONG_PACKET_MIN_LEN) - a partial
        parse recovers the serial and, when `product_class` is supplied (the long
        packet doesn't carry it; pass it from the device registry), the opening
        position; the status flags stay None until the short packet is seen."""
        info = cls(address=address, rssi=rssi, raw_manufacturer_data=[p.hex() for p in payloads])
        if not payloads:
            return info
        distinct = list({p for p in payloads})
        try:
            if len(distinct) >= 2:
                info._parse(combine_manufacturer_payloads(distinct))
            else:
                info._parse_long_packet_only(distinct[0], product_class)
        except Exception as exc:  # advertisement parsing must never crash a scan
            info.parse_error = f"{type(exc).__name__}: {exc}"
        return info

    def _parse_long_packet_only(self, packet: bytes, product_class: int | None) -> None:
        """Best-effort parse from a single (long) advertisement packet. Refusing
        outright would leave a resting drive unreadable, since an idle drive sends
        only this packet. The long packet's trailing 8 bytes are the serial number
        (cross-checked live against the QR/registry serial), and for product_class
        2 (Supramatic family) product_data[5]=packet[1] is the position byte and
        product_data[6]=packet[2] the maintenance byte - these live in the long
        packet, whereas the status flags (in_action, low_battery, relais, ...) sit
        in the short packet and stay None until it is seen. product_class cannot be
        read from the long packet alone, so the caller supplies it."""
        if len(packet) < LONG_PACKET_MIN_LEN:
            self.parse_error = (
                f"only 1 manufacturer-data packet seen ({len(packet)} bytes), too short to be the "
                "long packet that carries the serial/position - the drive splits its advertisement "
                "across two packets, and the second appears mainly around activity"
            )
            return

        # Serial is the last 8 bytes of the combined frame, i.e. of the long packet
        # (see _parse: data[17:25] with a 25-byte combined frame).
        self.serial_no = struct.unpack_from("<Q", packet, len(packet) - 8)[0]
        if product_class == 2:
            self.opening_progress_percent = packet[1] / 2.0
            self.maintenance_required = _bit(packet[2], 1)
        parsed = "serial and position" if product_class == 2 else "serial"
        self.parse_error = (
            f"only the long advertisement packet seen - an idle drive sends just this one; "
            f"{parsed} parsed, but the status flags need the second (status) packet, which "
            "appears mainly around activity"
        )

    def _parse(self, data: bytes) -> None:
        # BLEAdvertisementData.ParseData
        if len(data) < 4:
            self.parse_error = "not enough raw data for product class/ID"
            return
        product_id, product_class = data[2], data[3]
        self.product_class = product_class
        self.product_id = product_id
        self.product_name = PRODUCT_TYPE_NAMES.get((product_class, product_id)) or PRODUCT_TYPE_NAMES.get(
            (product_class, None)
        )

        if len(data) < 17:
            self.parse_error = (
                f"only {len(data)} of the required >=17 bytes seen "
                "(maybe not both advertisement packets were captured during the scan)"
            )
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
        # of the same device (see protocol.serial_no_from_qr_prefix).
        if len(data) >= 25:
            self.serial_no = struct.unpack_from("<Q", data, 17)[0]
