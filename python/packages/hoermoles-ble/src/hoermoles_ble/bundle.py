"""
Transportable credential bundle: the format used to move taught drives
(credentials + the non-secret product metadata) between this Python
implementation and other clients - primarily the web app, which cannot read
`~/.hoermoles/credentials/*.json` off the filesystem.

Deliberately a *separate, versioned wire format* rather than "just ship the
credentials file": a bundle can hold several drives at once, carries the
`devices.json` product metadata along (so the web app knows which menu table
applies without a BLE scan), and has a text form that fits into a QR code or a
URL fragment.

Two encodings, both round-trippable by the TypeScript port in
`spa/packages/hoermoles-ble-js/src/bundle.ts` - keep the two in sync, they
implement one spec:

    HMOLES1:<base64url(utf8 json)>            plaintext
    HMOLES1E:<base64url(binary envelope)>     passphrase-encrypted

The encrypted envelope is
`b"HM1E" || salt(16) || nonce(12) || AES-256-GCM(ciphertext||tag)`, key derived
via PBKDF2-HMAC-SHA256. Encryption is not optional decoration: a root key is a
physical door key, and the text form is meant to travel through QR codes, URL
fragments and chat messages, all of which get logged, cached and shoulder-surfed.
Plaintext export therefore stays available (it is convenient and often fine for
a QR code shown on a local screen) but callers should default to encrypting
anything that leaves the machine.

base64url is used without padding so the text form is safe in a URL fragment.

`serial_no` is carried as a *string*, not a JSON number, on purpose: Hoermann
serial numbers are uint64 (the live test device's is 302626026414510307), which
exceeds JavaScript's Number.MAX_SAFE_INTEGER. A JSON number would silently lose
its last digits when the web app parses it - caught exactly this way by the
shared test vectors.
"""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .credentials import Credentials
from .devices import DeviceInfo

BUNDLE_FORMAT = "hoermoles-credentials"
BUNDLE_VERSION = 1

PREFIX_PLAIN = "HMOLES1:"
PREFIX_ENCRYPTED = "HMOLES1E:"

_ENCRYPTED_MAGIC = b"HM1E"
_SALT_SIZE = 16
_NONCE_SIZE = 12
_KEY_SIZE = 32
# OWASP's 2023 floor for PBKDF2-HMAC-SHA256 is 600k; WebCrypto does the same work in
# the browser in well under a second, so there is no reason to go below it here.
_PBKDF2_ITERATIONS = 600_000


class BundleError(ValueError):
    """Malformed bundle: wrong prefix, bad base64, unknown version, or - for the
    encrypted form - a wrong passphrase (AES-GCM authentication failure)."""


@dataclass
class BundleEntry:
    """One drive in a bundle: the secret part (Credentials) plus, when known,
    the non-secret registry part (DeviceInfo). `device_info` is optional because
    a drive can have been registered without ever being scanned."""

    credentials: Credentials
    device_info: DeviceInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "device_address": self.credentials.device_address.upper(),
            "root_id": self.credentials.root_id,
            "root_key_hex": self.credentials.root_key.hex(),
            "qr_prefix": self.credentials.qr_prefix,
            "created_unix": self.credentials.created_unix,
        }
        # A user-chosen display name. Top-level (not under the product block), to
        # mirror the TypeScript port's flat layout and so it round-trips even
        # when the product type is unknown. On this side the value lives in
        # DeviceInfo.label, so it is only present once a drive has a DeviceInfo.
        if self.device_info is not None and self.device_info.label:
            entry["label"] = self.device_info.label
        if self.device_info is not None:
            entry["product_class"] = self.device_info.product_class
            entry["product_id"] = self.device_info.product_id
            entry["product_name"] = self.device_info.product_name
            # str(), not int - see the module docstring on uint64 vs JS numbers.
            serial_no = self.device_info.serial_no
            entry["serial_no"] = None if serial_no is None else str(serial_no)
        return entry

    @classmethod
    def from_dict(cls, entry: dict[str, Any]) -> BundleEntry:
        try:
            address = entry["device_address"]
            credentials = Credentials(
                device_address=address,
                root_id=int(entry["root_id"]),
                root_key=bytes.fromhex(entry["root_key_hex"]),
                qr_prefix=entry.get("qr_prefix", ""),
                created_unix=int(entry.get("created_unix", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BundleError(f"Malformed bundle entry: {exc}") from exc

        device_info = None
        if entry.get("product_class") is not None and entry.get("product_id") is not None:
            serial_no = entry.get("serial_no")
            device_info = DeviceInfo(
                device_address=address.upper(),
                product_class=int(entry["product_class"]),
                product_id=int(entry["product_id"]),
                product_name=entry.get("product_name"),
                # Accepts the legacy JSON-number form too, so a bundle written
                # before the string change still imports.
                serial_no=None if serial_no is None else int(serial_no),
                label=entry.get("label"),
            )
        # A label without any product info (theoretically possible from the web
        # app, though a registered drive always has product info) has nowhere to
        # be stored on this side - DeviceInfo requires a product - so it is
        # dropped rather than fabricating a placeholder product type.
        return cls(credentials=credentials, device_info=device_info)


def build_bundle(entries: list[BundleEntry]) -> dict[str, Any]:
    """The bundle as a plain dict - the single canonical JSON shape, shared by
    the file form, the plaintext text form and (after encryption) the encrypted
    text form."""
    return {
        "format": BUNDLE_FORMAT,
        "v": BUNDLE_VERSION,
        "devices": [entry.to_dict() for entry in entries],
    }


def parse_bundle(payload: dict[str, Any]) -> list[BundleEntry]:
    if not isinstance(payload, dict):
        raise BundleError("Bundle must be a JSON object.")
    if payload.get("format") != BUNDLE_FORMAT:
        raise BundleError(f"Not a hoermoles credential bundle (format={payload.get('format')!r}).")
    version = payload.get("v")
    if version != BUNDLE_VERSION:
        raise BundleError(f"Unsupported bundle version {version!r}, this build understands v{BUNDLE_VERSION}.")
    devices = payload.get("devices")
    if not isinstance(devices, list):
        raise BundleError("Bundle is missing a 'devices' list.")
    return [BundleEntry.from_dict(entry) for entry in devices]


def bundle_to_json(entries: list[BundleEntry]) -> str:
    """File form: pretty-printed JSON, for `--out bundle.json` and for the web
    app's file picker."""
    return json.dumps(build_bundle(entries), indent=2) + "\n"


def bundle_from_json(text: str) -> list[BundleEntry]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BundleError(f"Not valid JSON: {exc}") from exc
    return parse_bundle(payload)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as exc:
        raise BundleError(f"Malformed base64url payload: {exc}") from exc


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=_KEY_SIZE, salt=salt, iterations=_PBKDF2_ITERATIONS)
    return kdf.derive(passphrase.encode("utf-8"))


def encode_bundle(
    entries: list[BundleEntry],
    passphrase: str | None = None,
    *,
    _salt: bytes | None = None,
    _nonce: bytes | None = None,
) -> str:
    """Text form, for QR codes and URL fragments. With `passphrase`, the
    HMOLES1E form; without, the plaintext HMOLES1 form.

    `_salt`/`_nonce` exist solely so `interop.build_test_vectors()` can emit a
    reproducible encrypted vector for the TypeScript port to decrypt. Never pass
    them in real use: a reused salt/nonce pair under the same passphrase breaks
    AES-GCM outright.
    """
    raw = json.dumps(build_bundle(entries), separators=(",", ":")).encode("utf-8")
    if passphrase is None:
        return PREFIX_PLAIN + _b64url_encode(raw)

    salt = _salt if _salt is not None else secrets.token_bytes(_SALT_SIZE)
    nonce = _nonce if _nonce is not None else secrets.token_bytes(_NONCE_SIZE)
    ciphertext = AESGCM(_derive_key(passphrase, salt)).encrypt(nonce, raw, _ENCRYPTED_MAGIC)
    return PREFIX_ENCRYPTED + _b64url_encode(_ENCRYPTED_MAGIC + salt + nonce + ciphertext)


def is_encrypted_bundle(text: str) -> bool:
    """Whether `text` needs a passphrase - lets a caller (CLI, web app) prompt
    only when it actually has to."""
    return text.strip().startswith(PREFIX_ENCRYPTED)


def decode_bundle(text: str, passphrase: str | None = None) -> list[BundleEntry]:
    """Accepts every form a bundle can arrive in: the two text prefixes, a raw
    JSON file, or a URL carrying the text form in its fragment
    (`https://.../#import=HMOLES1E:...`) - the web app hands out such links, and
    users paste the whole URL rather than the payload."""
    text = text.strip()

    if "#import=" in text:
        text = text.split("#import=", 1)[1].strip()

    if text.startswith(PREFIX_ENCRYPTED):
        if passphrase is None:
            raise BundleError("This bundle is encrypted - a passphrase is required.")
        envelope = _b64url_decode(text[len(PREFIX_ENCRYPTED) :])
        offset = len(_ENCRYPTED_MAGIC)
        if len(envelope) <= offset + _SALT_SIZE + _NONCE_SIZE or not envelope.startswith(_ENCRYPTED_MAGIC):
            raise BundleError("Malformed encrypted bundle envelope.")
        salt = envelope[offset : offset + _SALT_SIZE]
        nonce = envelope[offset + _SALT_SIZE : offset + _SALT_SIZE + _NONCE_SIZE]
        ciphertext = envelope[offset + _SALT_SIZE + _NONCE_SIZE :]
        try:
            raw = AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, ciphertext, _ENCRYPTED_MAGIC)
        except Exception as exc:
            raise BundleError("Could not decrypt the bundle - wrong passphrase or corrupted data.") from exc
        return bundle_from_json(raw.decode("utf-8"))

    if text.startswith(PREFIX_PLAIN):
        return bundle_from_json(_b64url_decode(text[len(PREFIX_PLAIN) :]).decode("utf-8"))

    if text.startswith("{"):
        return bundle_from_json(text)

    raise BundleError(f"Unrecognized bundle format - expected '{PREFIX_PLAIN}', '{PREFIX_ENCRYPTED}' or JSON.")
