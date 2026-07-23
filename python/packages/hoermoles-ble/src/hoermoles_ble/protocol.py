"""
Pure protocol logic for the Hoermann BlueSecur "Signed" BLE channel.

Deliberately free of any BLE library dependency (no bleak, no GATT import) -
just byte framing, hashing/HMAC and RSA. That makes this module a direct
template for ports to C/C++ (mbedTLS/wolfSSL), JavaScript/TypeScript etc.:
each target language only needs to reproduce these functions with its own
crypto library and attach them to any GATT transport.

Source of the protocol details: decompiled 2_SAL.dll / 5_UTIL.dll / 4_HAL_Android.dll,
see reveng/ANALYSIS.md section 8.

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
from typing import List, Optional, Tuple

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

# EncryptedIO.ReadPackage: first byte of the (envelope-stripped) payload
ENCRYPTED_ACK_CONTINUE = 1
ENCRYPTED_ACK_COMPLETE = 2
ENCRYPTED_ACK_ERROR = 3

# SAL.BlueConnect.API.Devices.DeviceAction.CHANNEL_1..6, lower 16-bit word
CHANNEL_COMMAND_ID = {n: 0x0010 + n for n in range(1, 7)}

# Named gate action -> channel number, for the Supramatic/Rollmatic/SilentDrive
# product family (BlueApp.Core.Services.ChannelDefaultsService.TryGetDefaultsFor,
# ChannelCategory per DeviceAction.CHANNEL_n - identical for every product in
# that family except CHANNEL_6, which is absent on the plain SUPRAMATIC_4
# variant). CHANNEL_1 ("impulse", ChannelCategory.Other) is the factory-default
# toggle command and the only one verified live so far (see reveng/REVENG_REPORT.md);
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
    device (see reveng/ANALYSIS.md): prefix = 2-digit version + 7 digits
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
    length_field = 6 + len(payload) + SIZE_SIGNATURE
    header = struct.pack("<HHH", 0, REGISTER_ROOT_COMMAND_ID, length_field)
    message = header + payload
    signature = hmac.new(register_key, message + challenge, hashlib.sha256).digest()
    signed = message + signature
    return bytes([ROUTING_SIGNED]) + struct.pack("<H", len(signed) + 3) + signed


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

    @classmethod
    def parse(cls, payload: bytes) -> "ParsedSignedNotification":
        if len(payload) < 12:
            raise ValueError(f"Signed payload too short ({len(payload)} bytes): {payload.hex()}")
        challenge = payload[0:8]
        notif_type = struct.unpack_from("<H", payload, 8)[0]
        rest = payload[12:]
        root_id = None
        root_key_wire = None
        if notif_type == NOTIF_ROOT_KEY and len(rest) >= 2 + SIZE_ROOT_KEY:
            root_id = struct.unpack_from("<H", rest, 0)[0]
            root_key_wire = rest[2:2 + SIZE_ROOT_KEY]
        return cls(challenge=challenge, notif_type=notif_type, payload=rest,
                   root_id=root_id, root_key_wire=root_key_wire)


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
    length_field = 6 + len(payload) + SIZE_SIGNATURE
    header = struct.pack("<HHH", root_id, command_id, length_field)
    message = header + payload
    signature = hmac.new(root_key, message + challenge, hashlib.sha256).digest()
    signed = message + signature
    return bytes([ROUTING_SIGNED]) + struct.pack("<H", len(signed) + 3) + signed
