"""
Interpretation of the two "diagnostics" data sources the app exposes besides
the numbered operator menus (menu_settings.py):

- The security/access **audit log** (GET_LOG/LOG notifications, see
  protocol.build_get_log_frame/parse_log_entry_payload): admin/user actions,
  blocked login attempts, clock changes - SAL.BlueConnect.API.Devices.LogTag/
  DeviceLogInfo.
- **Service/diagnostics counters** (READ_SERVICE_DATA/SERVICE_DATA
  notifications, see protocol.build_read_service_data_frame/
  parse_service_data_payload): operating hours, door cycles, maintenance
  counters, ... - SAL.BlueConnect.API.Devices.Info.ServiceMaintenance.
  Interfaces.ServiceType/ServiceData.

Both are read-only diagnostics. Live-verified against a real Supramatic E4:
a full GET_LOG read correctly returned its two actual audit-log entries
(newest first), and READ_SERVICE_DATA returned plausible values for all 18
counters it sent (0-17 mapped here, plus one unmapped wire byte 18) - that
live check is also what caught a transcription error in SERVICE_TYPE_NAMES
(see the comment there). Field decoding for LogTag data blobs
(parse_log_fields) has not been individually exercised for every tag (only
REGISTER_ROOT and IMPULS_WITH_CLOCK occurred in the one log read so far).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

# SAL.BlueConnect.API.Devices.LogTag
LOG_TAG_NAMES: Dict[int, str] = {
    1: "REGISTER_ROOT",
    2: "RELAIS",
    3: "BLOCKED_ADMIN",
    4: "BLOCKED_USER",
    5: "BLOCKED_OTK",
    6: "EXECUTED_ADMIN_ACTION",
    7: "CLOCKTIME_CHANGED",
    8: "ACTION_REJECTED",
    9: "IMPULS_WITH_CLOCK",
}

# SAL.BlueConnect.API.Devices.Info.ServiceMaintenance.Interfaces.ServiceType
# Keys are the wire byte (0-17), values are the German [Description] of the
# ServiceType enum member that SAL.BlueConnect.API.Devices.Info.ServiceMaintenance.
# ServiceData.CreateServiceType(wireByte) maps it to - that switch is NOT the
# same as the ServiceType enum's own declared integer values (e.g. wire byte 17
# maps to ELEMENTS_COUNTER, not to the enum member that happens to equal 17,
# ENGINE_RUNTIME - caught by cross-checking a live read against this table).
# Product-specific subclasses like SupraMaticH4ServiceData add further
# meanings for wire bytes 18+ for their own product, NOT reproduced here -
# unmapped wire bytes are simply absent from this dict.
SERVICE_TYPE_NAMES: Dict[int, str] = {
    0: "PowerOnZaehler",
    1: "Betriebsstunden",
    2: "Betriebsstunden seit Wartung",
    3: "Anzahl Wartungen",
    4: "Vollstaendige Torzyklen seit Wartung",
    5: "Unvollstaendige Torzyklen seit Wartung",
    6: "Zeitpunkt Erstinbetriebnahme",
    7: "Torzyklen vollstaendig",
    8: "Torzyklen unvollstaendig",
    9: "Zeitpunkt Werksreset",
    10: "Anzahl Werksreset",
    11: "Zeitpunkt Nachlernfahrt Kraft",
    12: "Zeitpunkt Nachlernfahrt Position",
    13: "Torzyklen Nachlernfahrt Kraft",
    14: "Torzyklen Nachlernfahrt Position",
    15: "Zaehler Fahrbefehle",
    16: "Zaehler Reversierfahrten",
    17: "Anzahl Elemente",
}

# Service types whose Value is a proprietary Hoermann fixed-32-day-month
# timestamp encoding (UTIL.Helper.HoermannDateTime.FromHoermannTimeStamp), NOT
# reproduced here (only relevant to these specific counters, not to e.g.
# "Betriebsstunden"/operating hours) - values for these keys are returned as
# the raw uint32 wire value.
SERVICE_TYPE_IS_TIMESTAMP = {6, 9, 11, 12}

# SAL.BlueConnect.API.Devices.DeviceAction, lower 16-bit word - Signed-protocol
# members only (BLUECONTROL_* skipped: different device profile, unused in
# this library - see protocol.py module docstring). Where two members share a
# lower 16-bit word (REGISTER_ROOT vs. SET_REGISTER_KEY - Signed vs. Encrypted
# protocol), the first one wins, exactly like DeviceLogValueAction's linear
# enum scan.
_DEVICE_ACTION_MEMBERS = (
    ("ENABLE_NOTIFICATIONS", 0),
    ("REGISTER_ROOT", 65537),
    ("CHANNEL_1", 65553), ("CHANNEL_2", 65554), ("CHANNEL_3", 65555),
    ("CHANNEL_4", 65556), ("CHANNEL_5", 65557), ("CHANNEL_6", 65558),
    ("GET_LOG", 65569), ("SET_CLOCK", 65570), ("GET_CLOCK", 65571),
    ("GET_BLOCKLIST", 65572), ("BLOCK_ROOT", 65573), ("BLOCK_USER", 65574),
    ("BLOCK_OTK", 65575), ("GET_PROPERTIES", 65576), ("SET_PROPERTIES", 65577),
    ("SOFTWARE_VERSION", 65578), ("FACTORY_RESET", 65579),
    ("GET_SELECTED_PROPERTIES", 65580), ("SET_CLOCK_TIMEZONE", 65581),
    ("GET_CLOCK_TIMEZONE", 65582), ("ROOT_NAMES", 65585), ("REBOOT", 65586),
    ("DFU_RESET", 65587), ("SOFTWARE_VERSION_STRG", 65600),
    ("SOFTWARE_VERSION_DISPLAY", 65601), ("READ_SERVICE_DATA", 65602),
    ("READ_SERVICE_ERRORS", 65603), ("READ_PRODUCTION_DATA_STRG", 65604),
    ("READ_PRODUCTION_DATA_DISPLAY", 65605), ("GET_PRODUCT_SERIAL_NUMBER", 65606),
    ("SET_REGISTER_KEY", 131073),
    ("UNKNOWN", 0xFFFFFFFF),
)
DEVICE_ACTION_NAMES: Dict[int, str] = {}
for _name, _value in _DEVICE_ACTION_MEMBERS:
    _lower = _value & 0xFFFF
    DEVICE_ACTION_NAMES.setdefault(_lower, _name)

# SAL.BlueConnect.IO.Signed.SignedNotificationType (full enum)
SIGNED_NOTIFICATION_TYPE_NAMES: Dict[int, str] = {
    1: "GATE_STATE", 2: "ROOT_KEY", 3: "CLOCK_DATA", 4: "ENABLED",
    5: "REQUEST_CLOCK", 6: "LOG", 7: "LOG_END", 8: "BLOCK_ROOT",
    9: "BLOCK_USER", 10: "BLOCK_LIST", 11: "BLOCK_LIST_END", 12: "NAMES_LIST",
    13: "NAMES_LIST_END", 14: "FACTORY_RESET", 15: "SOFTWARE_VERSION",
    16: "PROPERTIES_LIST", 17: "PROPERTIES_LIST_END", 18: "PROPERTY_ACCEPTED",
    19: "PROPERTIES_INVALID", 20: "ROOT_REGISTRATION_POSSIBLE",
    21: "BLOCK_OTK", 22: "IMPULS_INVALID_CLOCK", 23: "SIGNATURE",
    24: "SIGNATURE_END", 25: "SERVICE_ERROR", 26: "SERVICE_ERROR_END",
    27: "SERVICE_DATA", 28: "SERVICE_DATA_END", 29: "SOFTWARE_VERSION_DISPLAY",
    30: "SOFTWARE_VERSION_CONTROL_UNIT", 31: "PRODUCTION_DATA_CONTROL_UNIT",
    32: "PRODUCTION_DATA_DISPLAY", 33: "CLOCKDATA_TIMEZONE",
    34: "PRODUCT_SERIAL_NUMBER", 65280: "TIME_EXPIRED", 65281: "TIME_INVALID",
    65283: "USER_OR_OTK_INVALID", 65284: "SECURITY_ERROR",
    65522: "UNKNOWN_ACTION", 65530: "TIMEZONE_NOK", 65531: "OTK_BLOCKLIST_FULL",
    65532: "ADMIN_INVALID", 65533: "MAX_USER", 65534: "INTERNAL_ERROR",
    65535: "FAILED",
}

# DeviceLogEntry.HET_CONSTANT_YEAR_2000: log-entry/log-field timestamps are
# seconds since 2000-01-01 UTC, NOT the ServiceType timestamp encoding above.
_LOG_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def log_timestamp_to_datetime(wire_timestamp: int) -> datetime:
    """DeviceLogEntry/DeviceLogValueTime: wire value is seconds since 2000-01-01 UTC."""
    return _LOG_EPOCH + timedelta(seconds=wire_timestamp)


def _id(data: bytes) -> int:
    return int.from_bytes(data, "little")


def _action_name(data: bytes) -> str:
    """DeviceLogValueAction: the low bit 0x100 marks "executed by a user/OTK key rather
    than an admin key" - stripped before the DEVICE_ACTION_NAMES lookup."""
    raw = _id(data)
    executed_by_user = bool(raw & 0x100)
    name = DEVICE_ACTION_NAMES.get(raw & ~0x100, f"UNKNOWN(0x{raw:04x})")
    return f"{name} (by user/OTK)" if executed_by_user else name


def _notification_name(data: bytes) -> str:
    raw = _id(data)
    return SIGNED_NOTIFICATION_TYPE_NAMES.get(raw, f"UNKNOWN(0x{raw:04x})")


def parse_log_fields(log_tag: int, data: bytes) -> Dict[str, Any]:
    """SAL.BlueConnect.API.Devices.DeviceLogInfo.ParseData: per-LogTag field layout within
    a log entry's data blob - mirrors the original's guard conditions and slice ranges
    exactly (including its apparent off-by-one quirks in a couple of branches, e.g. RELAIS
    reading a byte at offset 5 while only checking length >= 5) rather than "fixing" them,
    to stay behaviourally identical to the real app. Returns {} for tags/data it doesn't
    recognize rather than guessing."""
    fields: Dict[str, Any] = {}

    if log_tag == 1:  # REGISTER_ROOT
        if len(data) >= 2:
            fields["causing_admin_id"] = _id(data[0:2])

    elif log_tag == 2:  # RELAIS
        if len(data) < 2:
            return fields
        fields["causing_admin_id"] = _id(data[0:2])
        if len(data) < 4:
            return fields
        fields["user_id"] = _id(data[2:3])
        if len(data) >= 4:
            fields["otk_id"] = _id(data[3:5])
            if len(data) >= 5:
                fields["toggled_channel"] = _id(data[5:6])

    elif log_tag == 3:  # BLOCKED_ADMIN
        if len(data) >= 4:
            fields["causing_admin_id"] = _id(data[0:2])
            fields["admin_id"] = _id(data[2:4])

    elif log_tag == 4:  # BLOCKED_USER
        if len(data) < 2:
            return fields
        fields["causing_admin_id"] = _id(data[0:2])
        if len(data) >= 4:
            fields["user_id"] = _id(data[2:4])
            if len(data) >= 6:
                fields["otk_id"] = _id(data[4:6])

    elif log_tag == 5:  # BLOCKED_OTK
        if len(data) < 2:
            return fields
        fields["causing_admin_id"] = _id(data[0:2])
        if len(data) >= 4:
            fields["user_id"] = _id(data[2:4])
            if len(data) >= 5:
                fields["otk_id"] = _id(data[4:5])

    elif log_tag == 6:  # EXECUTED_ADMIN_ACTION
        if len(data) >= 2:
            fields["causing_admin_id"] = _id(data[0:2])
            if len(data) >= 4:
                fields["action"] = _action_name(data[2:4])

    elif log_tag == 7:  # CLOCKTIME_CHANGED
        if len(data) < 2:
            return fields
        fields["causing_admin_id"] = _id(data[0:2])
        if len(data) >= 6:
            fields["old_time"] = log_timestamp_to_datetime(_id(data[2:6]))
            if len(data) >= 10:
                fields["new_time"] = log_timestamp_to_datetime(_id(data[6:10]))

    elif log_tag == 8:  # ACTION_REJECTED
        if len(data) < 2:
            return fields
        fields["causing_admin_id"] = _id(data[0:2])
        if len(data) < 3:
            return fields
        fields["user_id"] = _id(data[2:3])
        if len(data) < 5:
            return fields
        fields["otk_id"] = _id(data[3:5])
        if len(data) >= 7:
            fields["action"] = _action_name(data[5:7])
            if len(data) >= 9:
                fields["notification"] = _notification_name(data[7:9])

    elif log_tag == 9:  # IMPULS_WITH_CLOCK
        if len(data) < 2:
            return fields
        fields["causing_admin_id"] = _id(data[0:2])
        if len(data) < 3:
            return fields
        fields["toggled_channel"] = _id(data[2:3])
        if len(data) >= 7:
            fields["old_time"] = log_timestamp_to_datetime(_id(data[3:7]))
            if len(data) >= 11:
                fields["new_time"] = log_timestamp_to_datetime(_id(data[7:11]))

    return fields
