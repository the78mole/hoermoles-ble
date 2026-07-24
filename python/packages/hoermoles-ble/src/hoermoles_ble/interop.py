"""
Language-neutral artifacts emitted from this reference implementation, for the
ports in other languages to consume (currently the TypeScript port under
`spa/packages/hoermoles-ble-js`).

Two artifacts, both written to `shared/` at the repository root by
`python/scripts/generate_shared.py` and both guarded by a pytest test that
regenerates them and compares - so a change here that is not reflected on disk
turns CI red instead of silently letting the ports drift:

`shared/test-vectors.json`
    Known-good inputs and outputs for every pure function in protocol.py.
    The TS port runs its vitest suite against exactly these bytes, which is
    what keeps the two implementations byte-identical rather than merely
    "both plausible". Everything in here is deterministic - no randomness, no
    wall clock - because a vector that cannot be reproduced is not a vector.

`shared/menu-tables.json`
    menu_settings.py's product tables as data. The web app needs the menu
    number/wire byte mapping and the parameter texts to render a settings
    editor; maintaining a second hand-written copy of ~60 menus per product in
    TypeScript would guarantee drift.

Byte strings are hex-encoded throughout (lowercase, no separators). Serial
numbers are strings, not JSON numbers: they are uint64 and exceed JavaScript's
Number.MAX_SAFE_INTEGER, so a JSON number would arrive in the browser with its
last digits rounded away (this is not hypothetical - it is how the mismatch was
found). See bundle.py, which carries them the same way for the same reason.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .advertisement import AdvertisementInfo
from .bundle import BundleEntry, bundle_to_json, encode_bundle
from .credentials import Credentials
from .devices import DeviceInfo
from .menu_settings import DRIVE_MENU_TABLES
from .protocol import (
    NotificationReassembler,
    ParsedSignedNotification,
    batch_menu_groups_for_selected_properties,
    build_get_log_frame,
    build_get_properties_frame,
    build_get_selected_properties_frame,
    build_read_service_data_frame,
    build_register_root_frame,
    build_registration_frame,
    build_set_properties_frame,
    build_switch_relais_frame,
    derive_root_key,
    parse_qr_code,
    product_class_and_id_from_qr_prefix,
    serial_no_from_qr_prefix,
)

# Fixed inputs for every frame-building vector. Deliberately not random and not
# "realistic looking" - distinct, easily eyeballed byte patterns make a failing
# diff readable.
_ROOT_ID = 0x0123
_ROOT_KEY = bytes(range(32))
_CHALLENGE = bytes.fromhex("0011223344556677")
_TIMESTAMP = 1784850177

# A real QR code prefix layout (version 3): 2-digit version, product class/id,
# 20-digit zero-padded serial, 2 trailing digits - see protocol.serial_no_from_qr_prefix.
_QR_PREFIX = "03" + "02" + "02" + "000" + "00302626026414510307" + "99"
# Minimal valid RSA SubjectPublicKeyInfo, base64 as it appears in the QR code.
# Only used to pin down parse_qr_code's prefix/DER split - the DER itself is
# opaque to that function.
_QR_DER_B64 = "MCowBQYDK2VwAyEAGb9ECWmEzf6FQbrBZ9w7lshQhqowtrbLDFw4rXAxZuE="


def _frame_vectors() -> list[dict[str, Any]]:
    return [
        {
            "name": "switch_relais_channel_1",
            "function": "build_switch_relais_frame",
            "args": {"root_id": _ROOT_ID, "channel": 1, "now": _TIMESTAMP},
            "frame": build_switch_relais_frame(_ROOT_ID, 1, _ROOT_KEY, _CHALLENGE, now=_TIMESTAMP).hex(),
        },
        {
            "name": "switch_relais_channel_6",
            "function": "build_switch_relais_frame",
            "args": {"root_id": _ROOT_ID, "channel": 6, "now": _TIMESTAMP},
            "frame": build_switch_relais_frame(_ROOT_ID, 6, _ROOT_KEY, _CHALLENGE, now=_TIMESTAMP).hex(),
        },
        {
            "name": "register_root_default_username",
            "function": "build_register_root_frame",
            "args": {"username": "ArnoNym"},
            "frame": build_register_root_frame(_ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "register_root_custom_username",
            "function": "build_register_root_frame",
            "args": {"username": "hoermoles"},
            "frame": build_register_root_frame(_ROOT_KEY, _CHALLENGE, username="hoermoles").hex(),
        },
        {
            "name": "get_properties",
            "function": "build_get_properties_frame",
            "args": {"root_id": _ROOT_ID},
            "frame": build_get_properties_frame(_ROOT_ID, _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "get_selected_properties_one_group",
            "function": "build_get_selected_properties_frame",
            "args": {"root_id": _ROOT_ID, "menu_groups": [16]},
            "frame": build_get_selected_properties_frame(_ROOT_ID, [16], _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "get_selected_properties_four_groups",
            "function": "build_get_selected_properties_frame",
            "args": {"root_id": _ROOT_ID, "menu_groups": [1, 2, 3, 4]},
            "frame": build_get_selected_properties_frame(_ROOT_ID, [1, 2, 3, 4], _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "set_properties_single",
            "function": "build_set_properties_frame",
            "args": {"root_id": _ROOT_ID, "settings": [[16, 1]]},
            "frame": build_set_properties_frame(_ROOT_ID, [(16, 1)], _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "set_properties_negative_value",
            "function": "build_set_properties_frame",
            "args": {"root_id": _ROOT_ID, "settings": [[2, -1]]},
            "frame": build_set_properties_frame(_ROOT_ID, [(2, -1)], _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "get_log",
            "function": "build_get_log_frame",
            "args": {"root_id": _ROOT_ID},
            "frame": build_get_log_frame(_ROOT_ID, _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "read_service_data",
            "function": "build_read_service_data_frame",
            "args": {"root_id": _ROOT_ID},
            "frame": build_read_service_data_frame(_ROOT_ID, _ROOT_KEY, _CHALLENGE).hex(),
        },
        {
            "name": "registration_encrypted",
            "function": "build_registration_frame",
            "args": {"rsa_encrypted_key_hex": (b"\xab" * 128).hex()},
            "frame": build_registration_frame(b"\xab" * 128).hex(),
        },
    ]


def _notification_vectors() -> list[dict[str, Any]]:
    """Raw Signed payloads (envelope already stripped) with their parsed form.
    Payloads are hand-built to the documented layout in protocol.py rather than
    captured, so each one isolates exactly one notification type."""
    challenge = "aabbccddeeff0011"
    cases = {
        # type 2 ROOT_KEY: root_id(2 LE) + 32-byte wire value
        "root_key": challenge + "0200" + "0000" + "0100" + ("55" * 32),
        # type 1 GATE_STATE, no extra payload
        "gate_state_empty": challenge + "0100" + "0000",
        # type 16 PROPERTIES_LIST: count(1) + count * [group(1), int16 LE]
        "properties_list": challenge + "1000" + "0000" + "02" + "01" + "0500" + "10" + "ffff",
        # type 17 PROPERTIES_LIST_END carrying no further data
        "properties_list_end_empty": challenge + "1100" + "0000",
        # type 6 LOG: dataLength(1), logTag(1), timestamp(uint32 LE), data
        "log_entry": challenge + "0600" + "0000" + "02" + "05" + "78563412" + "abcd",
        # type 7 LOG_END with no entry
        "log_end_empty": challenge + "0700" + "0000",
        # type 27 SERVICE_DATA: count(1) + count * [uint32 LE value, serviceType(1)]
        "service_data": challenge + "1b00" + "0000" + "02" + "2b000000" + "00" + "0c000000" + "01",
        # type 28 SERVICE_DATA_END with an explicit zero count
        "service_data_end_zero": challenge + "1c00" + "0000" + "00",
    }

    vectors = []
    for name, payload_hex in cases.items():
        parsed = ParsedSignedNotification.parse(bytes.fromhex(payload_hex))
        vectors.append(
            {
                "name": name,
                "payload": payload_hex,
                "expected": {
                    "challenge": parsed.challenge.hex(),
                    "notif_type": parsed.notif_type,
                    "payload": parsed.payload.hex(),
                    "root_id": parsed.root_id,
                    "root_key_wire": parsed.root_key_wire.hex() if parsed.root_key_wire is not None else None,
                    "properties": [list(pair) for pair in parsed.properties] if parsed.properties is not None else None,
                    "log_entry": (
                        [parsed.log_entry[0], parsed.log_entry[1], parsed.log_entry[2].hex()]
                        if parsed.log_entry is not None
                        else None
                    ),
                    "service_data": (
                        [list(pair) for pair in parsed.service_data] if parsed.service_data is not None else None
                    ),
                },
            }
        )
    return vectors


def _reassembler_vectors() -> list[dict[str, Any]]:
    """Each case is a list of raw notify events; the expectation is the list of
    complete (io_id, payload) messages the reassembler yields per event. These
    cover the three real-world shapes: one message per event, several messages
    in one event, and one message split across events."""
    cases: dict[str, list[str]] = {
        "single_complete_message": ["01" + "0600" + "112233"],
        "two_messages_in_one_event": ["01" + "0500" + "1122" + "02" + "0400" + "ff"],
        "message_split_across_events": ["01" + "0800" + "1122", "3344" + "55"],
        "trailing_padding_is_discarded": ["01" + "0500" + "1122" + "0000"],
        "encrypted_ack": ["02" + "0400" + "02"],
    }

    vectors = []
    for name, events in cases.items():
        reassembler = NotificationReassembler()
        expected = []
        for event in events:
            results = reassembler.feed(bytes.fromhex(event))
            expected.append([[io_id, payload.hex()] for io_id, payload in results])
        vectors.append({"name": name, "events": events, "expected_per_event": expected})
    return vectors


def _serial_str(serial_no: int | None) -> str | None:
    """uint64 serial numbers travel as strings - see the module docstring."""
    return None if serial_no is None else str(serial_no)


def _qr_vectors() -> list[dict[str, Any]]:
    qr_text = _QR_PREFIX + _QR_DER_B64
    prefix, der = parse_qr_code(qr_text)
    product = product_class_and_id_from_qr_prefix(prefix)
    return [
        {
            "name": "version_3_prefix",
            "qr_text": qr_text,
            "expected": {
                "prefix": prefix,
                "der": der.hex(),
                "serial_no": _serial_str(serial_no_from_qr_prefix(prefix)),
                "product_class": product[0] if product else None,
                "product_id": product[1] if product else None,
            },
        },
        {
            "name": "unknown_prefix_layout_is_rejected",
            "qr_text": "0102" + _QR_DER_B64,
            "expected": {
                "prefix": "0102",
                "der": der.hex(),
                "serial_no": None,
                "product_class": None,
                "product_id": None,
            },
        },
    ]


def _misc_vectors() -> dict[str, Any]:
    register_key = bytes(range(32))
    wire_value = bytes(range(255, 223, -1))
    return {
        "derive_root_key": {
            "register_key": register_key.hex(),
            "device_wire_value": wire_value.hex(),
            "expected_root_key": derive_root_key(register_key, wire_value).hex(),
        },
        "batch_menu_groups": [
            {"input": [1, 2, 3], "expected": batch_menu_groups_for_selected_properties([1, 2, 3])},
            {"input": [1, 2, 3, 4, 5], "expected": batch_menu_groups_for_selected_properties([1, 2, 3, 4, 5])},
            {"input": [99, 100, 101], "expected": batch_menu_groups_for_selected_properties([99, 100, 101])},
            {
                "input": [5, 3, 1, 101, 100, 99],
                "expected": batch_menu_groups_for_selected_properties([5, 3, 1, 101, 100, 99]),
            },
        ],
    }


def _advertisement_vectors() -> list[dict[str, Any]]:
    """Kept for the sake of completeness even though the web app cannot read
    advertisement data (Web Bluetooth gates that behind an experimental flag) -
    a native/flagged consumer can still use these, and generating them costs
    nothing."""
    payloads = [bytes.fromhex("0207b40202"), bytes.fromhex("11223344556677889900aabbccddeeff00")]
    info = AdvertisementInfo.from_scan("F1:26:AF:CC:41:86", -60, payloads)
    expected = {
        key: value for key, value in asdict(info).items() if key not in ("address", "rssi", "raw_manufacturer_data")
    }
    expected["serial_no"] = _serial_str(expected["serial_no"])
    return [
        {
            "name": "two_alternating_packets",
            "address": info.address,
            "rssi": info.rssi,
            "payloads": [p.hex() for p in payloads],
            "expected": expected,
        }
    ]


_BUNDLE_PASSPHRASE = "correct horse battery staple"
_BUNDLE_SALT = bytes(range(16))
_BUNDLE_NONCE = bytes(range(100, 112))


def _bundle_vectors() -> dict[str, Any]:
    """Credential bundles produced by this implementation, for the port to
    decode. The encrypted vector uses a pinned salt/nonce so it is reproducible -
    that is the only reason `encode_bundle`'s private `_salt`/`_nonce` hooks
    exist, and they must never be used outside this function."""
    entry = BundleEntry(
        credentials=Credentials(
            device_address="F1:26:AF:CC:41:86",
            root_id=1,
            root_key=bytes(range(32)),
            qr_prefix=_QR_PREFIX,
            created_unix=_TIMESTAMP,
        ),
        device_info=DeviceInfo(
            device_address="F1:26:AF:CC:41:86",
            product_class=2,
            product_id=2,
            product_name="Supramatic Serie 4",
            serial_no=302626026414510307,
            label="Garage",
        ),
    )
    return {
        "expected": {
            "device_address": "F1:26:AF:CC:41:86",
            "root_id": 1,
            "root_key": bytes(range(32)).hex(),
            "qr_prefix": _QR_PREFIX,
            "created_unix": _TIMESTAMP,
            "label": "Garage",
            "product_class": 2,
            "product_id": 2,
            "product_name": "Supramatic Serie 4",
            "serial_no": "302626026414510307",
        },
        "plain_text": encode_bundle([entry]),
        "json_file": bundle_to_json([entry]),
        "encrypted": {
            "passphrase": _BUNDLE_PASSPHRASE,
            "text": encode_bundle([entry], _BUNDLE_PASSPHRASE, _salt=_BUNDLE_SALT, _nonce=_BUNDLE_NONCE),
        },
    }


def build_test_vectors() -> dict[str, Any]:
    """The full `shared/test-vectors.json` payload."""
    return {
        "_comment": (
            "Generated by hoermoles_ble.interop via python/scripts/generate_shared.py - do not edit by hand. "
            "Byte strings are lowercase hex. Ports run their own test suites against these exact values."
        ),
        "constants": {
            "root_id": _ROOT_ID,
            "root_key": _ROOT_KEY.hex(),
            "challenge": _CHALLENGE.hex(),
            "timestamp": _TIMESTAMP,
        },
        "frames": _frame_vectors(),
        "notifications": _notification_vectors(),
        "reassembler": _reassembler_vectors(),
        "qr_codes": _qr_vectors(),
        "misc": _misc_vectors(),
        "advertisements": _advertisement_vectors(),
        "bundles": _bundle_vectors(),
    }


def build_menu_tables() -> dict[str, Any]:
    """The full `shared/menu-tables.json` payload: every product table from
    menu_settings.py, as plain data."""
    return {
        "_comment": (
            "Generated by hoermoles_ble.interop via python/scripts/generate_shared.py - do not edit by hand. "
            "Source of truth is hoermoles_ble/menu_settings.py; see its module docstring for what is "
            "live-verified against real hardware (only Supramatic E4, ProductClass=2/ProductID=2, and only "
            "the read direction) and what is merely derived from the decompiled app."
        ),
        "tables": [
            {
                "product_class": table.product_class,
                "product_id": table.product_id,
                "product_name": table.product_name,
                "software_numbers": list(table.software_numbers),
                "settings": [
                    {
                        "menu_number": setting.menu_number,
                        "menu_group": setting.menu_group,
                        "label": setting.label,
                        "label_en": setting.label_en,
                        "is_functional": setting.is_functional,
                        "parameters": [
                            {"value": parameter.value, "text": parameter.text, "is_default": parameter.is_default}
                            for parameter in setting.parameters
                        ],
                    }
                    for setting in table.settings
                ],
            }
            for table in DRIVE_MENU_TABLES
        ],
    }
