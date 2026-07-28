import hoermoles_ble.advertisement as adv
from hoermoles_ble.advertisement import AdvertisementInfo, combine_manufacturer_payloads


def test_bit_lsb_is_position_1():
    assert adv._bit(0b00000001, 1) is True
    assert adv._bit(0b00000010, 1) is False


def test_bit_msb_is_position_8():
    assert adv._bit(0b10000000, 8) is True
    assert adv._bit(0b01111111, 8) is False


def test_combine_manufacturer_payloads_orders_shortest_first():
    long_payload = b"\x01\x02\x03\x04"
    short_payload = b"\xaa\xbb"
    combined = combine_manufacturer_payloads([long_payload, short_payload])
    assert combined == adv.COMPANY_ID.to_bytes(2, "little") + short_payload + long_payload


def test_combine_manufacturer_payloads_dedupes():
    payload = b"\x01\x02"
    combined = combine_manufacturer_payloads([payload, payload])
    assert combined == adv.COMPANY_ID.to_bytes(2, "little") + payload


def _make_full_payload(product_id: int, product_class: int, serial_no: int = 123456789) -> bytes:
    """Builds a 25-byte post-company-ID payload as consumed by AdvertisementInfo._parse():
    [product_id][product_class][status_byte][product_data(13 bytes)][serial_no uint64 LE]."""
    data = bytearray(25)
    data[0] = product_id
    data[1] = product_class
    # status_byte (offset 2 within this slice, data[4] in the full company-ID-prefixed buffer):
    # bit1 is_blue_secur, bit3 clock_time_set, bit4 admin_teached, bit6 admins_can_be_teached,
    # bit8 opening_time
    data[2] = 0b10101101
    # product_data[1]: bit1 warning_time, bit3 low_battery, bit7 clear (teached_control=True), bit8 vacation_mode
    data[3] = 0b10000101
    data[7] = 80  # product_data[5] -> opening_progress_percent = 40.0
    data[8] = 0b00000001  # product_data[6] bit1 -> maintenance_required
    data[15:23] = serial_no.to_bytes(8, "little")
    return bytes(data)


def test_from_scan_no_payloads():
    info = AdvertisementInfo.from_scan("AA:BB:CC:DD:EE:FF", -60, [])
    assert info.parse_error is None
    assert info.product_class is None
    assert info.raw_manufacturer_data == []


def test_from_scan_single_short_packet_parses_nothing():
    # A lone packet shorter than the long (serial/position-carrying) packet can't
    # be decoded - honest parse_error, no faked fields, and no misleading
    # "scan longer" (an idle drive only ever sends the one packet).
    info = AdvertisementInfo.from_scan("AA:BB:CC:DD:EE:FF", -60, [b"\x01\x02"])
    assert info.parse_error is not None
    assert "too short" in info.parse_error
    assert "scan longer" not in info.parse_error
    assert info.serial_no is None
    assert info.opening_progress_percent is None


def test_from_scan_single_long_packet_with_class_hint_gives_position_and_serial():
    # The long packet alone (idle drive) still carries serial + position when the
    # product_class is known; status flags stay None (they're in the short packet).
    full = _make_full_payload(product_id=2, product_class=2, serial_no=302626026414510307)
    long_packet = full[6:23]  # combined data[8:25] - the 17-byte long packet
    info = AdvertisementInfo.from_scan("F1:26:AF:CC:41:86", -59, [long_packet], product_class=2)

    assert info.serial_no == 302626026414510307
    assert info.opening_progress_percent == 40.0
    assert info.maintenance_required is True
    # status flags need the short packet - deliberately left unknown
    assert info.admin_teached is None
    assert info.in_action is None
    assert info.low_battery is None
    assert info.parse_error is not None
    assert "long advertisement packet" in info.parse_error


def test_from_scan_single_long_packet_without_class_hint_gives_serial_only():
    full = _make_full_payload(product_id=2, product_class=2, serial_no=123456789)
    long_packet = full[6:23]
    info = AdvertisementInfo.from_scan("F1:26:AF:CC:41:86", -59, [long_packet])

    assert info.serial_no == 123456789  # class-independent, from the trailing 8 bytes
    assert info.opening_progress_percent is None  # needs the class to interpret
    assert info.maintenance_required is None
    assert info.parse_error is not None


def test_from_scan_two_payloads_too_short_sets_parse_error():
    info = AdvertisementInfo.from_scan("AA:BB:CC:DD:EE:FF", -60, [b"\x01", b"\x02\x03"])
    assert info.parse_error is not None
    assert ">=17" in info.parse_error


def test_from_scan_full_supramatic_payload():
    full = _make_full_payload(product_id=2, product_class=2)
    payloads = [full[:6], full[6:]]  # split arbitrarily into two "packets" like real scans
    info = AdvertisementInfo.from_scan("F1:26:AF:CC:41:86", -55, payloads)

    assert info.parse_error is None
    assert info.product_class == 2
    assert info.product_id == 2
    assert info.product_name == "Supramatic Serie 4"
    assert info.is_blue_secur is True
    assert info.clock_time_set is True
    assert info.admin_teached is True
    assert info.protection_active is False
    assert info.admins_can_be_teached is True
    assert info.in_action is False
    assert info.opening_time is True
    assert info.warning_time is True
    assert info.emergency_mode is False
    assert info.low_battery is True
    assert info.teached_control is True
    assert info.vacation_mode is True
    assert info.opening_progress_percent == 40.0
    assert info.maintenance_required is True
    assert info.serial_no == 123456789


def test_from_scan_het_product_class_uses_relais_fields():
    full = _make_full_payload(product_id=1, product_class=1)
    info = AdvertisementInfo.from_scan("AA:BB:CC:DD:EE:FF", -60, [full[:8], full[8:]])

    assert info.product_name == "HET"
    # product_data[0] is the status_byte itself (0b10101101): bit1 set, bit2 clear
    assert info.relais1_open is True
    assert info.relais2_open is False
    # HET doesn't set opening_progress_percent/maintenance_required (Supramatic-only branch)
    assert info.opening_progress_percent is None
    assert info.maintenance_required is None


def test_from_scan_unknown_product_falls_back_to_none_name():
    full = _make_full_payload(product_id=99, product_class=99)
    info = AdvertisementInfo.from_scan("AA:BB:CC:DD:EE:FF", -60, [full[:8], full[8:]])
    assert info.product_name is None


def test_from_scan_catches_parse_exception(monkeypatch):
    def _boom(_payloads):
        raise ValueError("synthetic failure")

    monkeypatch.setattr(adv, "combine_manufacturer_payloads", _boom)
    info = AdvertisementInfo.from_scan("AA:BB:CC:DD:EE:FF", -60, [b"\x01", b"\x02"])
    assert info.parse_error == "ValueError: synthetic failure"
