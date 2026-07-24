from datetime import datetime, timezone

import hoermoles_ble.device_log as dl


def test_log_timestamp_to_datetime_epoch():
    assert dl.log_timestamp_to_datetime(0) == datetime(2000, 1, 1, tzinfo=timezone.utc)


def test_log_timestamp_to_datetime_offset():
    # one day (86400s) after the 2000-01-01 epoch
    assert dl.log_timestamp_to_datetime(86400) == datetime(2000, 1, 2, tzinfo=timezone.utc)


def test_device_action_names_dedup_keeps_first():
    # REGISTER_ROOT (65537) and SET_REGISTER_KEY (131073) share the same lower
    # 16-bit word (1) - REGISTER_ROOT is declared first in _DEVICE_ACTION_MEMBERS
    # and must win per the "first one wins" linear-scan rule.
    assert dl.DEVICE_ACTION_NAMES[1] == "REGISTER_ROOT"


def test_device_action_names_known_value():
    assert dl.DEVICE_ACTION_NAMES[65576 & 0xFFFF] == "GET_PROPERTIES"


def test_service_type_names_wire_byte_17_is_elements_counter():
    # regression check for the live-verified fix: wire byte 17 is
    # "Anzahl Elemente", NOT "Antriebslaufzeit"/ENGINE_RUNTIME.
    assert dl.SERVICE_TYPE_NAMES[17] == "Anzahl Elemente"


def test_service_type_is_timestamp_set():
    assert dl.SERVICE_TYPE_IS_TIMESTAMP == {6, 9, 11, 12}


# --- parse_log_fields: LogTag 1 REGISTER_ROOT ---


def test_parse_log_fields_register_root():
    fields = dl.parse_log_fields(1, bytes([0x05, 0x00]))
    assert fields == {"causing_admin_id": 5}


def test_parse_log_fields_register_root_too_short():
    assert dl.parse_log_fields(1, b"\x01") == {}


# --- LogTag 2 RELAIS (has the intentional off-by-one: byte at offset 5 read
# while only length >= 5 is checked, per the module docstring) ---


def test_parse_log_fields_relais_full():
    data = bytes([1, 0, 2, 3, 0, 4])
    fields = dl.parse_log_fields(2, data)
    assert fields["causing_admin_id"] == 1
    assert fields["user_id"] == 2
    assert fields["otk_id"] == 3
    assert fields["toggled_channel"] == 4


def test_parse_log_fields_relais_admin_only():
    assert dl.parse_log_fields(2, bytes([1, 0])) == {"causing_admin_id": 1}


def test_parse_log_fields_relais_too_short():
    assert dl.parse_log_fields(2, b"\x01") == {}


# --- LogTag 3 BLOCKED_ADMIN ---


def test_parse_log_fields_blocked_admin():
    fields = dl.parse_log_fields(3, bytes([1, 0, 2, 0]))
    assert fields == {"causing_admin_id": 1, "admin_id": 2}


def test_parse_log_fields_blocked_admin_too_short():
    assert dl.parse_log_fields(3, bytes([1, 0, 2])) == {}


# --- LogTag 4 BLOCKED_USER ---


def test_parse_log_fields_blocked_user_full():
    fields = dl.parse_log_fields(4, bytes([1, 0, 2, 0, 3, 0]))
    assert fields == {"causing_admin_id": 1, "user_id": 2, "otk_id": 3}


def test_parse_log_fields_blocked_user_admin_only():
    assert dl.parse_log_fields(4, bytes([1, 0])) == {"causing_admin_id": 1}


# --- LogTag 5 BLOCKED_OTK ---


def test_parse_log_fields_blocked_otk_full():
    fields = dl.parse_log_fields(5, bytes([1, 0, 2, 0, 3]))
    assert fields == {"causing_admin_id": 1, "user_id": 2, "otk_id": 3}


# --- LogTag 6 EXECUTED_ADMIN_ACTION (exercises _action_name) ---


def test_parse_log_fields_executed_admin_action():
    # DeviceLogValueAction fields are 2 bytes wide on the wire - only the lower
    # 16-bit word of DeviceAction (as keyed in DEVICE_ACTION_NAMES) fits here.
    action_bytes = (65576 & 0xFFFF).to_bytes(2, "little")  # GET_PROPERTIES
    fields = dl.parse_log_fields(6, bytes([1, 0]) + action_bytes)
    assert fields == {"causing_admin_id": 1, "action": "GET_PROPERTIES"}


def test_parse_log_fields_executed_admin_action_by_user():
    action_bytes = ((65576 & 0xFFFF) | 0x100).to_bytes(2, "little")
    fields = dl.parse_log_fields(6, bytes([1, 0]) + action_bytes)
    assert fields["action"] == "GET_PROPERTIES (by user/OTK)"


def test_parse_log_fields_executed_admin_action_unknown():
    fields = dl.parse_log_fields(6, bytes([1, 0]) + (0xDEAD & 0xFFFF).to_bytes(2, "little"))
    assert fields["action"] == f"UNKNOWN(0x{0xDEAD:04x})"


# --- LogTag 7 CLOCKTIME_CHANGED ---


def test_parse_log_fields_clocktime_changed():
    old_time = (0).to_bytes(4, "little")
    new_time = (86400).to_bytes(4, "little")
    fields = dl.parse_log_fields(7, bytes([1, 0]) + old_time + new_time)
    assert fields["causing_admin_id"] == 1
    assert fields["old_time"] == datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert fields["new_time"] == datetime(2000, 1, 2, tzinfo=timezone.utc)


# --- LogTag 8 ACTION_REJECTED (exercises _notification_name) ---


def test_parse_log_fields_action_rejected_full():
    action_bytes = (65572 & 0xFFFF).to_bytes(2, "little")  # GET_BLOCKLIST
    notif_bytes = (65534).to_bytes(2, "little")  # INTERNAL_ERROR
    data = bytes([1, 0, 2, 3, 0]) + action_bytes + notif_bytes
    fields = dl.parse_log_fields(8, data)
    assert fields["causing_admin_id"] == 1
    assert fields["user_id"] == 2
    assert fields["otk_id"] == 3
    assert fields["action"] == "GET_BLOCKLIST"
    assert fields["notification"] == "INTERNAL_ERROR"


def test_parse_log_fields_action_rejected_partial():
    assert dl.parse_log_fields(8, bytes([1, 0])) == {"causing_admin_id": 1}


# --- LogTag 9 IMPULS_WITH_CLOCK ---


def test_parse_log_fields_impuls_with_clock_full():
    old_time = (0).to_bytes(4, "little")
    new_time = (86400).to_bytes(4, "little")
    data = bytes([1, 0, 3]) + old_time + new_time
    fields = dl.parse_log_fields(9, data)
    assert fields["causing_admin_id"] == 1
    assert fields["toggled_channel"] == 3
    assert fields["old_time"] == datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert fields["new_time"] == datetime(2000, 1, 2, tzinfo=timezone.utc)


def test_parse_log_fields_impuls_with_clock_partial():
    fields = dl.parse_log_fields(9, bytes([1, 0, 3]))
    assert fields == {"causing_admin_id": 1, "toggled_channel": 3}


# --- unknown log tag ---


def test_parse_log_fields_unknown_tag_returns_empty():
    assert dl.parse_log_fields(99, bytes(range(10))) == {}
