"""
Pure protocol logic for the Hoermann BlueSecur "Signed" BLE channel.

Deliberately free of any BLE library dependency (no bleak, no GATT import) -
just byte framing, hashing/HMAC and RSA. That makes this module a direct
template for ports to C/C++ (mbedTLS/wolfSSL), JavaScript/TypeScript etc.:
each target language only needs to reproduce these functions with its own
crypto library and attach them to any GATT transport.

Source of the protocol details: decompiled 2_SAL.dll / 5_UTIL.dll / 4_HAL_Android.dll
from the official Hoermann BlueSecur Android app.

GATT ("BlueConnect" service):
    Service       669a9001-0008-968f-e311-6050405558b3
    TX (Write)    669a900c-0008-968f-e311-6050405558b3
    RX (Notify)   669a900a-0008-968f-e311-6050405558b3

Both written commands AND incoming notifications carry the same outer envelope
(SAL.BlueConnect.IO.Router.States.ReceivingState.ReadChunk):
    [ioId(1 byte)][length(2 bytes LE, including these 3 bytes)][payload(length-3 bytes)]
ioId selects the sub-reader (1=Signed, 2=Encrypted, 3=BlueControl). Only AFTER
stripping this envelope does the Signed-specific format (challenge+type+payload)
follow for ioId=1; for ioId=2 (Encrypted) the remainder is just a single status
byte (see EncryptedIO.ReadPackage).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

BC_SERVICE = "669a9001-0008-968f-e311-6050405558b3"
BC_TX = "669a900c-0008-968f-e311-6050405558b3"
BC_RX = "669a900a-0008-968f-e311-6050405558b3"

GATT_WRITE_CHUNK_SIZE = 20  # SAL.BlueConnect.IO.*.PAYLOAD_SIZE

ROUTING_SIGNED = 0x01       # SAL.BlueConnect.IO.Signed        (everyday commands, HMAC)
ROUTING_ENCRYPTED = 0x02    # SAL.BlueConnect.IO.Encrypted     (one-time registration, RSA)
ROUTING_BLUECONTROL = 0x03  # SAL.BlueConnect.IO.BlueControl   (different device profile, unused here)

# SAL.BlueConnect.IO.Signed.SignedNotificationType (excerpt, relevant to this module)
NOTIF_GATE_STATE = 1
NOTIF_ROOT_KEY = 2
NOTIF_ENABLED = 4
NOTIF_PROPERTIES_LIST = 16      # one chunk of menu/parameter settings (see PropertyListItem below)
NOTIF_PROPERTIES_LIST_END = 17  # last chunk - may or may not carry data itself
NOTIF_PROPERTY_ACCEPTED = 18    # ack for SET_PROPERTIES
NOTIF_PROPERTIES_INVALID = 19   # nack for SET_PROPERTIES (e.g. out-of-range value)
NOTIF_LOG = 6                   # one audit-log entry (see LogEntryNotification below)
NOTIF_LOG_END = 7               # last chunk - may or may not carry an entry itself
NOTIF_SERVICE_DATA = 27         # one chunk of service/diagnostics counters (see ServiceNotification below)
NOTIF_SERVICE_DATA_END = 28     # last chunk - may or may not carry data itself

# EncryptedIO.ReadPackage: first byte of the (envelope-stripped) payload
ENCRYPTED_ACK_CONTINUE = 1
ENCRYPTED_ACK_COMPLETE = 2
ENCRYPTED_ACK_ERROR = 3

# SAL.BlueConnect.API.Devices.DeviceAction.CHANNEL_1..6, lower 16-bit word
CHANNEL_COMMAND_ID = {n: 0x0010 + n for n in range(1, 7)}

# SAL.BlueConnect.API.Devices.DeviceAction.{GET,SET,GET_SELECTED}_PROPERTIES, lower 16-bit word.
# Read/write the drive's menu-configurable parameters (Hoermann's classic numbered "menu 20",
# "menu 25", ... hand-transmitter menus, exposed to the app as "operator settings" instead of
# button sequences on the drive itself) - see build_get_properties_frame/build_set_properties_frame
# below and hoermoles_ble.menu_settings for the Supramatic E4 menu-number/wire-byte table.
GET_PROPERTIES_COMMAND_ID = 0x0028
SET_PROPERTIES_COMMAND_ID = 0x0029
GET_SELECTED_PROPERTIES_COMMAND_ID = 0x002C

# SAL.BlueConnect.API.Devices.DeviceAction.GET_LOG/READ_SERVICE_DATA, lower 16-bit word.
# GET_LOG reads the drive's security/access audit log (admin/user actions, blocked
# attempts, clock changes - see hoermoles_ble.device_log.LogTag); READ_SERVICE_DATA reads
# diagnostics counters (operating hours, door cycles, ...) - see
# hoermoles_ble.device_log.ServiceType. Both are "menu 9x"-adjacent app features
# ("Diagnosedaten"/log view), but travel over their own notification types, not
# GET_PROPERTIES/SET_PROPERTIES.
GET_LOG_COMMAND_ID = 0x0021
READ_SERVICE_DATA_COMMAND_ID = 0x0042

# Named gate action -> channel number, for the Supramatic/Rollmatic/SilentDrive
# product family (BlueApp.Core.Services.ChannelDefaultsService.TryGetDefaultsFor,
# ChannelCategory per DeviceAction.CHANNEL_n - identical for every product in
# that family except CHANNEL_6, which is absent on the plain SUPRAMATIC_4
# variant). CHANNEL_1 ("impulse", ChannelCategory.Other) is the factory-default
# toggle command and the only one verified live so far;
# "light"/"partial"/"open"/"close"/"ventilation" are structurally derived from
# the decompiled defaults table but not yet confirmed against real hardware.
GATE_ACTIONS = {
    "impulse": 1,      # ChannelCategory.Other - factory default, toggles open/stop/close
    "light": 2,        # ChannelCategory.Light
    "partial": 3,      # ChannelCategory.Partial (Teiloeffnung)
    "open": 4,         # ChannelCategory.Open (Richtungswahl Tor-AUF)
    "close": 5,        # ChannelCategory.Close (Richtungswahl Tor-ZU)
    "ventilation": 6,  # ChannelCategory.VentilationPosition - not present on every model
}

# DeviceAction.REGISTER_ROOT = 65537 = 0x10001, lower 16-bit word
REGISTER_ROOT_COMMAND_ID = 0x0001

SIZE_SIGNATURE = 32   # SignedIOConstants.SIZE_SIGNATURE (HMAC-SHA256)
SIZE_ROOT_KEY = 32    # SignedIOConstants.SIZE_ROOT_KEY
SIZE_USER_NAME = 16   # SignedIOConstants.SIZE_USER_NAME
DEFAULT_REGISTER_USERNAME = "ArnoNym"  # SAL.BlueConnect.IO.Signed.SignedWriter.createCommand, hardcoded


def parse_qr_code(text: str) -> tuple[str, bytes]:
    """Splits the QR code content into the numeric prefix (version/product
    info/serial no.) and the RSA SubjectPublicKeyInfo DER block (base64-encoded
    in the QR code)."""
    text = text.strip()
    i = 0
    while i < len(text) and text[i].isdigit():
        i += 1
    prefix = text[:i]
    der = base64.b64decode(text[i:])
    return prefix, der


def serial_no_from_qr_prefix(prefix: str) -> Optional[int]:
    """Extracts the serial number from the QR code prefix - determined
    empirically and verified live against the BLE advertisement of the same
    device: prefix = 2-digit version + 7 digits
    (product class/ID, unclear) + 20-digit zero-padded serial number (uint64)
    + 2 remaining digits. Only verified on ONE device/QR code - other product
    versions might have a different prefix layout, so this is defensive: it
    returns None instead of guessing if the length doesn't match exactly.

    AdvertisementInfo.serial_no from the advertisement (advertisement.py)
    yields the same serial number - this lets a QR code be matched to a
    scanned device without any connection/registration."""
    if len(prefix) != 31 or not prefix.isdigit():
        return None
    return int(prefix[9:29])


def product_class_and_id_from_qr_prefix(prefix: str) -> Optional[Tuple[int, int]]:
    """Extracts (product_class, product_id) from the QR code prefix - see
    SAL.BlueConnect.API.Devices.Register.RegisterDeviceData.ParseDataForVersion3
    (only version 3 reproduced here, like serial_no_from_qr_prefix above):
    offset 2 (2 hex digits) is product_class, offset 4 (2 hex digits) is
    product_id (e.g. "0302020000..." -> version 3, class=2, id=2 - matches
    hoermoles_ble.advertisement.PRODUCT_TYPE_NAMES/AdvertisementInfo.product_class
    /product_id for the same device). Returns None for any other version or a
    malformed prefix rather than guessing - versions 1/2/4 use a different,
    not yet reproduced layout."""
    if len(prefix) != 31 or not prefix.isdigit() or prefix[:2] != "03":
        return None
    try:
        return int(prefix[2:4], 16), int(prefix[4:6], 16)
    except ValueError:
        return None


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def chunk(data: bytes, size: int = GATT_WRITE_CHUNK_SIZE):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def build_registration_frame(rsa_encrypted_key: bytes) -> bytes:
    """SAL.BlueConnect.IO.Encrypted.EncryptedIO.startSetRegisterKey:
    [0x02][len16 LE][32 random bytes, RSA-PKCS1v1.5-encrypted]."""
    return bytes([ROUTING_ENCRYPTED]) + struct.pack("<H", len(rsa_encrypted_key) + 3) + rsa_encrypted_key


def derive_root_key(register_key: bytes, device_wire_value: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.RootKeyNotification.ReadStream:
    final root key = (value sent by the device) XOR (our registration random value)."""
    return xor_bytes(device_wire_value, register_key)


def _build_signed_frame(root_id: int, command_id: int, payload: bytes,
                         key: bytes, challenge: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.SignedCommandBase.Serialize, shared by every Signed-protocol
    command: [RootId(2 LE)][Command(2 LE)][Length incl. these 6 bytes(2 LE)][payload]
    [HMAC-SHA256(key, everything above ++ challenge)(32)], wrapped in the outer
    [ioId][length] envelope (see module docstring)."""
    length_field = 6 + len(payload) + SIZE_SIGNATURE
    header = struct.pack("<HHH", root_id, command_id, length_field)
    message = header + payload
    signature = hmac.new(key, message + challenge, hashlib.sha256).digest()
    signed = message + signature
    return bytes([ROUTING_SIGNED]) + struct.pack("<H", len(signed) + 3) + signed


def build_register_root_frame(register_key: bytes, challenge: bytes,
                               username: str = DEFAULT_REGISTER_USERNAME) -> bytes:
    """SAL.BlueConnect.IO.Signed.RegisterRootCmd (KeyType.REGISTER_KEY) + SignedCommandBase.Serialize.

    Second, necessary part of the registration (SAL.BlueConnect.API.Keys.KeyChain.RegisterRoot
    sends both commands as one sequence): after the RSA-encrypted
    SET_REGISTER_KEY message, the drive additionally expects this
    REGISTER_ROOT command, HMAC-signed with the same `register_key` we
    generated for the RSA encryption (RootId=0, since no RootID from the
    device is known yet). The username is hardcoded in the original.
    """
    username_bytes = username.encode("utf-8")[:SIZE_USER_NAME].ljust(SIZE_USER_NAME, b"\x00")
    payload = b"\x00" + username_bytes  # 1 byte UserID (always 0) + 16 byte username
    return _build_signed_frame(0, REGISTER_ROOT_COMMAND_ID, payload, register_key, challenge)


class NotificationReassembler:
    """Reassembles the outer [ioId][length] envelope (see module docstring).

    A single raw BLE notify event can contain multiple messages (the drive
    e.g. sends a small ENABLED message followed directly by padding/trailing
    bytes in the same ATT packet), or a message can span multiple notify
    events - `feed()` therefore returns a list (possibly empty) of complete
    (io_id, payload) tuples and keeps incomplete remainders internally for the
    next call.
    """

    _VALID_IO_IDS = {ROUTING_SIGNED, ROUTING_ENCRYPTED, ROUTING_BLUECONTROL}

    def __init__(self) -> None:
        self._io_id: Optional[int] = None
        self._declared_length: Optional[int] = None
        self._buffer = bytearray()

    def feed(self, data: bytes) -> List[Tuple[int, bytes]]:
        results: List[Tuple[int, bytes]] = []
        pos = 0
        while pos < len(data):
            if self._io_id is None:
                if len(data) - pos < 3:
                    break  # remainder is no longer a complete header - discard (padding)
                io_id = data[pos]
                declared_length = struct.unpack_from("<H", data, pos + 1)[0]
                if io_id not in self._VALID_IO_IDS or declared_length < 3:
                    break  # not a valid message start - presumably padding, discard the rest
                self._io_id = io_id
                self._declared_length = declared_length
                pos += 3
            payload_size = self._declared_length - 3
            needed = payload_size - len(self._buffer)
            take = max(0, min(needed, len(data) - pos))
            self._buffer.extend(data[pos:pos + take])
            pos += take
            if len(self._buffer) >= payload_size:
                results.append((self._io_id, bytes(self._buffer)))
                self._io_id = None
                self._declared_length = None
                self._buffer = bytearray()
            else:
                break  # message not yet complete, the rest arrives in the next feed()
        return results


@dataclass
class ParsedSignedNotification:
    """A decoded notification of the Signed sub-protocol (io_id=1).

    SAL.BlueConnect.IO.Signed.SignedReader.ReadPackage: after the outer
    [ioId][length] envelope (see NotificationReassembler) follows an 8-byte
    challenge (nonce for the next HMAC signature), then type (2 bytes) +
    reserved (2 bytes) + type-specific payload.
    """
    challenge: bytes
    notif_type: int
    payload: bytes
    root_id: Optional[int] = None
    root_key_wire: Optional[bytes] = None
    properties: Optional[List[Tuple[int, int]]] = None
    log_entry: Optional[Tuple[int, int, bytes]] = None
    service_data: Optional[List[Tuple[int, int]]] = None

    @classmethod
    def parse(cls, payload: bytes) -> "ParsedSignedNotification":
        if len(payload) < 12:
            raise ValueError(f"Signed payload too short ({len(payload)} bytes): {payload.hex()}")
        challenge = payload[0:8]
        notif_type = struct.unpack_from("<H", payload, 8)[0]
        rest = payload[12:]
        root_id = None
        root_key_wire = None
        properties = None
        log_entry = None
        service_data = None
        if notif_type == NOTIF_ROOT_KEY and len(rest) >= 2 + SIZE_ROOT_KEY:
            root_id = struct.unpack_from("<H", rest, 0)[0]
            root_key_wire = rest[2:2 + SIZE_ROOT_KEY]
        elif notif_type in (NOTIF_PROPERTIES_LIST, NOTIF_PROPERTIES_LIST_END):
            properties = parse_properties_list_payload(rest)
        elif notif_type in (NOTIF_LOG, NOTIF_LOG_END):
            log_entry = parse_log_entry_payload(rest)
        elif notif_type in (NOTIF_SERVICE_DATA, NOTIF_SERVICE_DATA_END):
            service_data = parse_service_data_payload(rest)
        return cls(challenge=challenge, notif_type=notif_type, payload=rest,
                   root_id=root_id, root_key_wire=root_key_wire, properties=properties,
                   log_entry=log_entry, service_data=service_data)


def build_switch_relais_frame(root_id: int, channel: int, root_key: bytes, challenge: bytes,
                               now: Optional[int] = None) -> bytes:
    """SAL.BlueConnect.IO.Signed.SwitchRelaisCmd + SignedCommandBase.Serialize,
    key type ROOT_KEY (payload = 8-byte Unix timestamp, no UserID/validity block).

    Returns the finished, ROUTING_SIGNED-wrapped frame, ready to be chunked via
    `chunk()` and written to BC_TX.
    """
    if channel not in CHANNEL_COMMAND_ID:
        raise ValueError(f"channel must be 1..6, was {channel}")
    command_id = CHANNEL_COMMAND_ID[channel]
    payload = struct.pack("<Q", int(now if now is not None else time.time()))
    return _build_signed_frame(root_id, command_id, payload, root_key, challenge)


def build_get_properties_frame(root_id: int, root_key: bytes, challenge: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.EmptyCmd bound to DeviceAction.GET_PROPERTIES: zero-length
    payload. Triggers the drive to stream back its *entire* menu/parameter table as one or
    more PROPERTIES_LIST notifications, terminated by a PROPERTIES_LIST_END notification
    (see parse_properties_list_payload() and ParsedSignedNotification.properties).
    Structurally derived from Hoermann.BleApp.Core.Services.ApplianceSettingsService.ReadSettings
    (no filter) / SAL.BlueConnect.API.Devices.BaseBluetoothService.RefreshProperties.
    Live-verified against a real Supramatic E4 (F1:26:AF:CC:41:86): all 60 documented menu
    groups (1-99) plus 101 came back with plausible values matching the `02.ai`-scoped
    SUPRAMATIC_E4_MENU_TABLE - see hoermoles_ble.menu_settings for two additional, undocumented
    wire groups (0 and 100) observed in that same read.
    """
    return _build_signed_frame(root_id, GET_PROPERTIES_COMMAND_ID, b"", root_key, challenge)


def build_get_selected_properties_frame(root_id: int, menu_groups: Sequence[int],
                                         root_key: bytes, challenge: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.GetSelectedPropertiesCmd: payload is just the raw list of
    requested menu-group bytes (see hoermoles_ble.menu_settings for the Supramatic E4
    menu-number/wire-byte table), no count prefix, padded with 0xFF up to a minimum of 4
    entries (`GetSelectedPropertiesCmd` constructor pads unconditionally - reason for the
    minimum of 4 specifically is not documented in the decompiled source).

    The official app also caps each such request at 4 menu groups and starts a new one
    whenever crossing the group-100 boundary (`BaseBluetoothService.RefreshProperties`,
    overridden identically in `BlueSecurService` - i.e. this is NOT a HET-only quirk, it
    applies to the whole Supramatic/Rollmatic/SilentDrive family too). This is NOT just an
    app convention - live-confirmed against a real Supramatic E4 that mixing a <100 and a
    >=100 group in one request makes the drive drop the connection instead of answering
    (see batch_menu_groups_for_selected_properties(), which callers should use to build
    `menu_groups` batches for this function).
    """
    if not (1 <= len(menu_groups) <= 4):
        raise ValueError(f"menu_groups must have 1..4 entries per request, had {len(menu_groups)}")
    groups = list(menu_groups) + [0xFF] * (4 - len(menu_groups))
    return _build_signed_frame(root_id, GET_SELECTED_PROPERTIES_COMMAND_ID, bytes(groups),
                                root_key, challenge)


def batch_menu_groups_for_selected_properties(menu_groups: Sequence[int]) -> List[List[int]]:
    """Splits menu groups into batches suitable for build_get_selected_properties_frame():
    SAL.BlueConnect.API.Devices.BaseBluetoothService.RefreshProperties sorts the requested
    groups ascending, then starts a new batch of at most 4 whenever crossing from a group
    < 100 to one >= 100. Required, not optional - see build_get_selected_properties_frame().
    """
    sorted_groups = sorted(menu_groups)
    batches: List[List[int]] = []
    current: List[int] = []
    for i, group in enumerate(sorted_groups):
        crosses_100 = i != 0 and group >= 100 and sorted_groups[i - 1] < 100
        if current and (len(current) % 4 == 0 or crosses_100):
            batches.append(current)
            current = []
        current.append(group)
    if current:
        batches.append(current)
    return batches


def build_set_properties_frame(root_id: int, settings: Sequence[Tuple[int, int]],
                                root_key: bytes, challenge: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.PropertyListCmd: [count(1)] + count * [menu_group(1),
    value(int16 LE, signed)]. `settings` is a sequence of (menu_group, value) pairs (see
    hoermoles_ble.menu_settings for the Supramatic E4 menu-number/wire-byte table and valid
    values per menu).

    The official app batches writes into groups of at most 4 settings per frame
    (`BaseBluetoothService.SetPropertiesForDevice`) - whether that's a hard device limit or
    just an app convention is unconfirmed; callers writing more than 4 settings at once
    should mirror that batching to stay on the safe side. The read direction (GET_PROPERTIES/
    GET_SELECTED_PROPERTIES) is live-verified; this write direction is NOT yet verified
    against real hardware.
    """
    if not settings:
        raise ValueError("settings must not be empty")
    payload = bytes([len(settings)])
    for menu_group, value in settings:
        payload += bytes([menu_group]) + struct.pack("<h", value)
    return _build_signed_frame(root_id, SET_PROPERTIES_COMMAND_ID, payload, root_key, challenge)


def parse_properties_list_payload(payload: bytes) -> List[Tuple[int, int]]:
    """SAL.BlueConnect.IO.Signed.reader.Notifications.PropertyListItem.ReadStream:
    [count(1)] + count * [menu_group(1), value(int16 LE, signed)]. Both PROPERTIES_LIST and
    PROPERTIES_LIST_END notifications use this same format - PROPERTIES_LIST_END may carry a
    final chunk of settings itself, or be empty and only signal the end of the stream."""
    if not payload:
        return []
    count = payload[0]
    settings = []
    offset = 1
    for _ in range(count):
        menu_group = payload[offset]
        value = struct.unpack_from("<h", payload, offset + 1)[0]
        settings.append((menu_group, value))
        offset += 3
    return settings


def build_get_log_frame(root_id: int, root_key: bytes, challenge: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.EmptyCmd bound to DeviceAction.GET_LOG: zero-length payload.
    Triggers the drive to stream back its security/access audit log (admin/user actions,
    blocked attempts, clock changes - see hoermoles_ble.device_log.LogTag) as one or more
    LOG notifications, terminated by a LOG_END notification. Live-verified against a real
    Supramatic E4."""
    return _build_signed_frame(root_id, GET_LOG_COMMAND_ID, b"", root_key, challenge)


def build_read_service_data_frame(root_id: int, root_key: bytes, challenge: bytes) -> bytes:
    """SAL.BlueConnect.IO.Signed.EmptyCmd bound to DeviceAction.READ_SERVICE_DATA:
    zero-length payload. Triggers the drive to stream back its diagnostics counters
    (operating hours, door cycles, ... - see hoermoles_ble.device_log.ServiceType) as one or
    more SERVICE_DATA notifications, terminated by a SERVICE_DATA_END notification.
    Live-verified against a real Supramatic E4."""
    return _build_signed_frame(root_id, READ_SERVICE_DATA_COMMAND_ID, b"", root_key, challenge)


def parse_log_entry_payload(payload: bytes) -> Optional[Tuple[int, int, bytes]]:
    """SAL.BlueConnect.IO.Signed.reader.Notifications.LogEntryNotification.ReadStream:
    [dataLength(1)][logTag(1)][timestamp(uint32 LE)][data(dataLength bytes)] - a single log
    entry per notification (unlike the properties/service-data list formats, which pack
    several entries per notification). Both LOG and LOG_END use this format - LOG_END may
    carry a final entry itself, or be empty (returns None) and only signal the end of the
    stream. Returns (log_tag, timestamp_raw, data) - see hoermoles_ble.device_log for how to
    interpret these (LogTag names, per-tag field layout, timestamp conversion)."""
    if not payload:
        return None
    data_length = payload[0]
    log_tag = payload[1]
    timestamp_raw = struct.unpack_from("<I", payload, 2)[0]
    data = payload[6:6 + data_length]
    return log_tag, timestamp_raw, data


def parse_service_data_payload(payload: bytes) -> List[Tuple[int, int]]:
    """SAL.BlueConnect.IO.Signed.reader.Notifications.ServiceNotification.ReadStream:
    [count(1)] + count * [value(uint32 LE), serviceType(1)] - note the value/key order is
    swapped compared to parse_properties_list_payload(). Both SERVICE_DATA and
    SERVICE_DATA_END notifications use this format. Returns [(service_type, value), ...] -
    see hoermoles_ble.device_log.SERVICE_TYPE_NAMES for human-readable descriptions."""
    if not payload or payload[0] == 0:
        return []
    count = payload[0]
    result = []
    offset = 1
    for _ in range(count):
        value = struct.unpack_from("<I", payload, offset)[0]
        service_type = payload[offset + 4]
        result.append((service_type, value))
        offset += 5
    return result
