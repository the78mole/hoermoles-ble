"""Tests for hoermoles_ble.protocol - pure byte-framing logic, no BLE/crypto deps."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct

import pytest
from hoermoles_ble import protocol as p


# --- QR code prefix parsing --------------------------------------------------


def test_parse_qr_code_splits_prefix_and_der():
    der_bytes = b"some-der-bytes"
    text = "0302020000030262602641451030700" + base64.b64encode(der_bytes).decode()
    prefix, der = p.parse_qr_code(text)
    assert prefix == "0302020000030262602641451030700"
    assert der == der_bytes


def test_parse_qr_code_strips_whitespace():
    der_bytes = b"xyz"
    text = "  123" + base64.b64encode(der_bytes).decode() + "\n"
    prefix, der = p.parse_qr_code(text)
    assert prefix == "123"
    assert der == der_bytes


def test_serial_no_from_qr_prefix_valid():
    # 31 digits: 2 version + 7 + 20-digit serial + 2 - matches the real device's prefix
    prefix = "0302020000030262602641451030700"[:31]
    assert p.serial_no_from_qr_prefix(prefix) == int(prefix[9:29])


@pytest.mark.parametrize(
    "prefix",
    [
        "123",  # too short
        "1" * 32,  # too long
        "a" * 31,  # not all digits
    ],
)
def test_serial_no_from_qr_prefix_invalid_returns_none(prefix):
    assert p.serial_no_from_qr_prefix(prefix) is None


def test_product_class_and_id_from_qr_prefix_version3():
    # "03" version, "02" class, "02" id (hex digits) - matches the live-tested device
    prefix = "0302020000030262602641451030700"
    assert p.product_class_and_id_from_qr_prefix(prefix) == (2, 2)


def test_product_class_and_id_from_qr_prefix_hex_digits():
    # the whole prefix must be decimal digits (checked via .isdigit()), so only
    # digit-only substrings ever reach the hex parse - "23" -> 0x23 = 35, "45" -> 0x45 = 69
    prefix = "03" + "23" + "45" + "0" * 25
    assert len(prefix) == 31
    assert p.product_class_and_id_from_qr_prefix(prefix) == (0x23, 0x45)


@pytest.mark.parametrize(
    "prefix",
    [
        "0102020000030262602641451030700",  # wrong version
        "123",  # too short
        "a" * 31,  # not digits
    ],
)
def test_product_class_and_id_from_qr_prefix_invalid_returns_none(prefix):
    assert p.product_class_and_id_from_qr_prefix(prefix) is None


# --- basic byte helpers -------------------------------------------------------


def test_xor_bytes():
    assert p.xor_bytes(b"\x00\xff\x0f", b"\xff\xff\x00") == b"\xff\x00\x0f"


def test_chunk_exact_multiple():
    data = bytes(range(40))
    chunks = list(p.chunk(data, size=20))
    assert chunks == [data[0:20], data[20:40]]


def test_chunk_with_remainder():
    data = bytes(range(25))
    chunks = list(p.chunk(data, size=20))
    assert chunks == [data[0:20], data[20:25]]


def test_chunk_default_size_matches_gatt_chunk_size():
    data = bytes(range(45))
    chunks = list(p.chunk(data))
    assert all(len(c) <= p.GATT_WRITE_CHUNK_SIZE for c in chunks)
    assert b"".join(chunks) == data


# --- registration frames ------------------------------------------------------


def test_build_registration_frame_envelope():
    encrypted = b"\x01" * 256
    frame = p.build_registration_frame(encrypted)
    assert frame[0] == p.ROUTING_ENCRYPTED
    declared_len = struct.unpack_from("<H", frame, 1)[0]
    assert declared_len == len(encrypted) + 3
    assert frame[3:] == encrypted


def test_derive_root_key_is_xor():
    register_key = bytes(range(32))
    device_wire_value = bytes(reversed(range(32)))
    root_key = p.derive_root_key(register_key, device_wire_value)
    assert root_key == p.xor_bytes(device_wire_value, register_key)
    # XOR is its own inverse
    assert p.xor_bytes(root_key, register_key) == device_wire_value


def test_build_register_root_frame_structure_and_hmac():
    register_key = bytes(range(32))
    challenge = bytes(range(8))
    frame = p.build_register_root_frame(register_key, challenge, username="Bob")

    assert frame[0] == p.ROUTING_SIGNED
    body = frame[3:]
    root_id, command_id, length_field = struct.unpack_from("<HHH", body, 0)
    assert root_id == 0
    assert command_id == p.REGISTER_ROOT_COMMAND_ID
    assert length_field == len(body)

    payload = body[6 : -p.SIZE_SIGNATURE]
    signature = body[-p.SIZE_SIGNATURE :]
    message = body[: -p.SIZE_SIGNATURE]
    expected_signature = hmac.new(register_key, message + challenge, hashlib.sha256).digest()
    assert signature == expected_signature

    assert payload[0:1] == b"\x00"  # UserID always 0
    username_bytes = payload[1 : 1 + p.SIZE_USER_NAME]
    assert username_bytes == b"Bob" + b"\x00" * (p.SIZE_USER_NAME - 3)


def test_build_register_root_frame_truncates_long_username():
    frame = p.build_register_root_frame(bytes(32), bytes(8), username="x" * 100)
    payload = frame[3:][6 : -p.SIZE_SIGNATURE]
    username_bytes = payload[1 : 1 + p.SIZE_USER_NAME]
    assert len(username_bytes) == p.SIZE_USER_NAME
    assert username_bytes == b"x" * p.SIZE_USER_NAME


# --- channel switching ---------------------------------------------------------


def test_build_switch_relais_frame_structure_and_hmac():
    root_key = bytes(range(32))
    challenge = bytes(range(8))
    frame = p.build_switch_relais_frame(root_id=7, channel=1, root_key=root_key, challenge=challenge, now=12345)

    assert frame[0] == p.ROUTING_SIGNED
    body = frame[3:]
    root_id, command_id, length_field = struct.unpack_from("<HHH", body, 0)
    assert root_id == 7
    assert command_id == p.CHANNEL_COMMAND_ID[1]
    assert length_field == len(body)

    payload = body[6 : -p.SIZE_SIGNATURE]
    assert struct.unpack("<Q", payload)[0] == 12345

    message = body[: -p.SIZE_SIGNATURE]
    signature = body[-p.SIZE_SIGNATURE :]
    assert signature == hmac.new(root_key, message + challenge, hashlib.sha256).digest()


def test_build_switch_relais_frame_rejects_invalid_channel():
    with pytest.raises(ValueError, match="channel must be 1..6"):
        p.build_switch_relais_frame(1, channel=7, root_key=bytes(32), challenge=bytes(8))


def test_channel_command_id_covers_1_through_6():
    assert p.CHANNEL_COMMAND_ID == {n: 0x10 + n for n in range(1, 7)}


def test_gate_actions_map_to_expected_channels():
    assert p.GATE_ACTIONS == {
        "impulse": 1,
        "light": 2,
        "partial": 3,
        "open": 4,
        "close": 5,
        "ventilation": 6,
    }


# --- NotificationReassembler ---------------------------------------------------


def _make_envelope(io_id: int, payload: bytes) -> bytes:
    return bytes([io_id]) + struct.pack("<H", len(payload) + 3) + payload


def test_reassembler_single_message_in_one_feed():
    reassembler = p.NotificationReassembler()
    payload = b"hello world"
    data = _make_envelope(p.ROUTING_SIGNED, payload)
    results = reassembler.feed(data)
    assert results == [(p.ROUTING_SIGNED, payload)]


def test_reassembler_message_split_across_feeds():
    reassembler = p.NotificationReassembler()
    payload = b"0123456789"
    data = _make_envelope(p.ROUTING_SIGNED, payload)
    first, second = data[:5], data[5:]

    assert reassembler.feed(first) == []
    assert reassembler.feed(second) == [(p.ROUTING_SIGNED, payload)]


def test_reassembler_multiple_messages_in_one_feed():
    reassembler = p.NotificationReassembler()
    msg1 = _make_envelope(p.ROUTING_SIGNED, b"aaa")
    msg2 = _make_envelope(p.ROUTING_ENCRYPTED, b"bb")
    results = reassembler.feed(msg1 + msg2)
    assert results == [(p.ROUTING_SIGNED, b"aaa"), (p.ROUTING_ENCRYPTED, b"bb")]


def test_reassembler_discards_invalid_io_id():
    reassembler = p.NotificationReassembler()
    garbage = bytes([0xFF]) + struct.pack("<H", 10) + b"\x00" * 7
    assert reassembler.feed(garbage) == []


def test_reassembler_discards_short_trailing_header():
    reassembler = p.NotificationReassembler()
    msg = _make_envelope(p.ROUTING_SIGNED, b"ok")
    trailing_padding = b"\xff\xff"  # < 3 bytes, not a full header
    assert reassembler.feed(msg + trailing_padding) == [(p.ROUTING_SIGNED, b"ok")]


# --- ParsedSignedNotification ---------------------------------------------------


def _make_signed_payload(challenge: bytes, notif_type: int, rest: bytes) -> bytes:
    return challenge + struct.pack("<H", notif_type) + b"\x00\x00" + rest


def test_parsed_signed_notification_too_short_raises():
    with pytest.raises(ValueError, match="too short"):
        p.ParsedSignedNotification.parse(b"\x00" * 5)


def test_parsed_signed_notification_enabled_has_no_extras():
    challenge = bytes(range(8))
    payload = _make_signed_payload(challenge, p.NOTIF_ENABLED, b"")
    notif = p.ParsedSignedNotification.parse(payload)
    assert notif.challenge == challenge
    assert notif.notif_type == p.NOTIF_ENABLED
    assert notif.root_id is None
    assert notif.root_key_wire is None
    assert notif.properties is None
    assert notif.log_entry is None
    assert notif.service_data is None


def test_parsed_signed_notification_root_key():
    challenge = bytes(range(8))
    root_key_wire = bytes(range(32))
    rest = struct.pack("<H", 42) + root_key_wire
    payload = _make_signed_payload(challenge, p.NOTIF_ROOT_KEY, rest)
    notif = p.ParsedSignedNotification.parse(payload)
    assert notif.root_id == 42
    assert notif.root_key_wire == root_key_wire


def test_parsed_signed_notification_properties_list():
    challenge = bytes(range(8))
    rest = bytes([1]) + bytes([5]) + struct.pack("<h", -3)
    payload = _make_signed_payload(challenge, p.NOTIF_PROPERTIES_LIST, rest)
    notif = p.ParsedSignedNotification.parse(payload)
    assert notif.properties == [(5, -3)]


def test_parsed_signed_notification_log():
    challenge = bytes(range(8))
    rest = bytes([2, 9]) + struct.pack("<I", 100) + b"\x01\x02"
    payload = _make_signed_payload(challenge, p.NOTIF_LOG, rest)
    notif = p.ParsedSignedNotification.parse(payload)
    assert notif.log_entry == (9, 100, b"\x01\x02")


def test_parsed_signed_notification_service_data():
    challenge = bytes(range(8))
    rest = bytes([1]) + struct.pack("<I", 43) + bytes([1])
    payload = _make_signed_payload(challenge, p.NOTIF_SERVICE_DATA, rest)
    notif = p.ParsedSignedNotification.parse(payload)
    assert notif.service_data == [(1, 43)]


# --- properties frames ---------------------------------------------------------


def test_build_get_properties_frame_zero_length_payload():
    frame = p.build_get_properties_frame(1, bytes(32), bytes(8))
    body = frame[3:]
    _, command_id, length_field = struct.unpack_from("<HHH", body, 0)
    assert command_id == p.GET_PROPERTIES_COMMAND_ID
    assert length_field == 6 + p.SIZE_SIGNATURE  # zero payload


def test_build_get_selected_properties_frame_pads_to_four():
    frame = p.build_get_selected_properties_frame(1, [5, 6], bytes(32), bytes(8))
    body = frame[3:]
    payload = body[6 : -p.SIZE_SIGNATURE]
    assert payload == bytes([5, 6, 0xFF, 0xFF])


def test_build_get_selected_properties_frame_exactly_four_no_padding():
    frame = p.build_get_selected_properties_frame(1, [1, 2, 3, 4], bytes(32), bytes(8))
    body = frame[3:]
    payload = body[6 : -p.SIZE_SIGNATURE]
    assert payload == bytes([1, 2, 3, 4])


@pytest.mark.parametrize("groups", [[], [1, 2, 3, 4, 5]])
def test_build_get_selected_properties_frame_rejects_bad_length(groups):
    with pytest.raises(ValueError, match="1..4 entries"):
        p.build_get_selected_properties_frame(1, groups, bytes(32), bytes(8))


def test_batch_menu_groups_splits_at_four():
    batches = p.batch_menu_groups_for_selected_properties([1, 2, 3, 4, 5])
    assert batches == [[1, 2, 3, 4], [5]]


def test_batch_menu_groups_splits_at_100_boundary():
    batches = p.batch_menu_groups_for_selected_properties([101, 39])
    assert batches == [[39], [101]]


def test_batch_menu_groups_sorts_input():
    batches = p.batch_menu_groups_for_selected_properties([50, 10, 30])
    assert batches == [[10, 30, 50]]


def test_batch_menu_groups_boundary_and_four_together():
    # 5 groups below 100 (splits at 4) then 2 groups >= 100 (own batch, also
    # split at 4 if there were more than 4 of them)
    groups = [1, 2, 3, 4, 5, 101, 102]
    batches = p.batch_menu_groups_for_selected_properties(groups)
    assert batches == [[1, 2, 3, 4], [5], [101, 102]]


def test_build_set_properties_frame_payload_format():
    frame = p.build_set_properties_frame(1, [(5, -3), (6, 100)], bytes(32), bytes(8))
    body = frame[3:]
    payload = body[6 : -p.SIZE_SIGNATURE]
    assert payload[0] == 2
    assert payload[1] == 5
    assert struct.unpack_from("<h", payload, 2)[0] == -3
    assert payload[4] == 6
    assert struct.unpack_from("<h", payload, 5)[0] == 100


def test_build_set_properties_frame_rejects_empty():
    with pytest.raises(ValueError, match="must not be empty"):
        p.build_set_properties_frame(1, [], bytes(32), bytes(8))


def test_parse_properties_list_payload_roundtrip():
    frame = p.build_set_properties_frame(1, [(5, -3), (6, 100)], bytes(32), bytes(8))
    body = frame[3:]
    payload = body[6 : -p.SIZE_SIGNATURE]
    assert p.parse_properties_list_payload(payload) == [(5, -3), (6, 100)]


def test_parse_properties_list_payload_empty():
    assert p.parse_properties_list_payload(b"") == []


# --- log / service-data frames --------------------------------------------------


def test_build_get_log_frame_zero_length_payload():
    frame = p.build_get_log_frame(1, bytes(32), bytes(8))
    body = frame[3:]
    _, command_id, length_field = struct.unpack_from("<HHH", body, 0)
    assert command_id == p.GET_LOG_COMMAND_ID
    assert length_field == 6 + p.SIZE_SIGNATURE


def test_build_read_service_data_frame_zero_length_payload():
    frame = p.build_read_service_data_frame(1, bytes(32), bytes(8))
    body = frame[3:]
    _, command_id, length_field = struct.unpack_from("<HHH", body, 0)
    assert command_id == p.READ_SERVICE_DATA_COMMAND_ID
    assert length_field == 6 + p.SIZE_SIGNATURE


def test_parse_log_entry_payload_roundtrip():
    data = b"\x01\x02\x03"
    payload = bytes([len(data), 9]) + struct.pack("<I", 12345) + data
    assert p.parse_log_entry_payload(payload) == (9, 12345, data)


def test_parse_log_entry_payload_empty_returns_none():
    assert p.parse_log_entry_payload(b"") is None


def test_parse_service_data_payload_roundtrip():
    payload = bytes([2]) + struct.pack("<I", 43) + bytes([1]) + struct.pack("<I", 99) + bytes([0])
    assert p.parse_service_data_payload(payload) == [(1, 43), (0, 99)]


@pytest.mark.parametrize("payload", [b"", bytes([0])])
def test_parse_service_data_payload_empty_returns_empty_list(payload):
    assert p.parse_service_data_payload(payload) == []
