"""
High-level client: connects the transport (BleTransport) to the pure
protocol logic (protocol.py) and the RSA crypto (crypto_rsa.py).

Everything a new caller (Home Assistant integration, custom script,
fingerprint-reader bridge, ...) needs is this class plus a Credentials
instance - no BLE or crypto details required.
"""
from __future__ import annotations

import asyncio
import secrets
from typing import Callable, Optional

from .credentials import Credentials
from .crypto_rsa import load_device_public_key, rsa_pkcs1v15_encrypt
from .protocol import (
    ENCRYPTED_ACK_COMPLETE,
    ENCRYPTED_ACK_CONTINUE,
    ENCRYPTED_ACK_ERROR,
    NOTIF_ROOT_KEY,
    ROUTING_ENCRYPTED,
    ROUTING_SIGNED,
    NotificationReassembler,
    ParsedSignedNotification,
    build_register_root_frame,
    build_registration_frame,
    build_switch_relais_frame,
    chunk,
    derive_root_key,
    parse_qr_code,
)
from .transport import BleTransport


class RegistrationTimeout(TimeoutError):
    """The drive did not respond (in time) to the registration attempt.

    Most common cause: the advertisement bit `AdminsCanBeTeached` is False,
    i.e. the drive already has an admin and won't accept a new root
    registration until it has been reset via menu 19/parameter 02.
    See reveng/ANALYSIS.md section 8.2.
    """


class HoermannClient:
    def __init__(self, transport: BleTransport, on_log: Optional[Callable[[str], None]] = None):
        self._transport = transport
        self._on_log = on_log or (lambda msg: None)
        self._reassembler = NotificationReassembler()
        self._last_signed: Optional[ParsedSignedNotification] = None
        self._last_encrypted_ack: Optional[int] = None
        self._signed_event = asyncio.Event()
        self._encrypted_event = asyncio.Event()

    async def __aenter__(self) -> "HoermannClient":
        await self._transport.connect()
        await self._transport.start_notify(self._on_notify)
        return self

    async def __aexit__(self, *exc_info) -> None:
        try:
            await self._transport.stop_notify()
        except Exception as exc:
            self._on_log(f"WARNING: stop_notify failed during cleanup ({exc}), "
                         "the connection was likely already gone")
        await self._transport.disconnect()

    def _on_notify(self, data: bytes) -> None:
        self._on_log(f"RAW notification ({len(data)} bytes): {data.hex()}")
        for io_id, payload in self._reassembler.feed(data):
            if io_id == ROUTING_SIGNED:
                try:
                    notif = ParsedSignedNotification.parse(payload)
                except ValueError as exc:
                    self._on_log(f"WARNING: {exc}")
                    continue
                self._on_log(f"Signed notification type={notif.notif_type} "
                             f"challenge={notif.challenge.hex()} payload={notif.payload.hex()}")
                self._last_signed = notif
                self._signed_event.set()
            elif io_id == ROUTING_ENCRYPTED:
                status = payload[0] if payload else None
                self._on_log(f"Encrypted acknowledgement status={status}")
                self._last_encrypted_ack = status
                self._encrypted_event.set()
            else:
                self._on_log(f"Notification with unhandled io_id={io_id}: {payload.hex()}")

    async def _wait_for_signed(self, predicate: Callable[[ParsedSignedNotification], bool],
                                timeout: float) -> ParsedSignedNotification:
        async def _loop():
            while True:
                if self._last_signed is not None and predicate(self._last_signed):
                    return self._last_signed
                self._signed_event.clear()
                await self._signed_event.wait()
        return await asyncio.wait_for(_loop(), timeout=timeout)

    async def _wait_for_encrypted_complete(self, timeout: float) -> None:
        """Waits for the EncryptedIO acknowledgement (SAL.BlueConnect.IO.Encrypted.EncryptedIO.ReadPackage):
        status byte 1=keep waiting (timer is restarted), 2=done/success, 3=error."""
        async def _loop():
            while True:
                if self._last_encrypted_ack is not None:
                    status = self._last_encrypted_ack
                    self._last_encrypted_ack = None
                    if status == ENCRYPTED_ACK_COMPLETE:
                        return
                    if status == ENCRYPTED_ACK_ERROR:
                        raise RegistrationTimeout(
                            "The drive acknowledged SET_REGISTER_KEY with an error status."
                        )
                    if status == ENCRYPTED_ACK_CONTINUE:
                        continue  # keep waiting, as ReceivingState does via timer restart
                self._encrypted_event.clear()
                await self._encrypted_event.wait()
        await asyncio.wait_for(_loop(), timeout=timeout)

    async def wait_for_any_notification(self, timeout: float = 10.0) -> ParsedSignedNotification:
        """Waits for the first Signed notification after connecting (typically
        ENABLED right after subscribing to notifications) - returns the current
        challenge, needed for the next signed command."""
        return await self._wait_for_signed(lambda n: True, timeout)

    async def _write_chunked(self, frame: bytes, inter_chunk_delay: float = 0.0) -> None:
        # NO delay between packets: tested live that the drive disconnects
        # roughly 100-150ms after the first chunk, regardless of the number of
        # chunks - behaves like a fixed time window for the whole message, not
        # a "too fast" problem.
        for part in chunk(frame):
            await self._transport.write(part)
            if inter_chunk_delay:
                await asyncio.sleep(inter_chunk_delay)

    async def register(self, qr_text: str, device_address: str, timeout: float = 15.0) -> Credentials:
        """One-time QR code registration (phase 1, reveng/ANALYSIS.md section 8).
        Assumes the drive is currently accepting a new registration
        (advertisement bit AdminsCanBeTeached=True, e.g. right after a reset
        via menu 19/parameter 02).

        Sends two commands as a sequence (SAL.BlueConnect.API.Keys.KeyChain.RegisterRoot):
        first SET_REGISTER_KEY (RSA), then - only AFTER its acknowledgement -
        REGISTER_ROOT (HMAC-signed with the same register_key).
        """
        prefix, der = parse_qr_code(qr_text)
        device_pubkey = load_device_public_key(der)
        register_key = secrets.token_bytes(32)
        encrypted = rsa_pkcs1v15_encrypt(device_pubkey, register_key)
        self._on_log(f"QR prefix: {prefix}, RSA key: {device_pubkey.key_size} bit")

        await self._write_chunked(build_registration_frame(encrypted))

        try:
            await self._wait_for_encrypted_complete(timeout=20.0)
        except asyncio.TimeoutError as exc:
            raise RegistrationTimeout(
                "No acknowledgement received for SET_REGISTER_KEY - the drive is presumably "
                "not currently accepting a new registration (AdminsCanBeTeached=False)."
            ) from exc

        # Second, necessary part of the sequence - HMAC-signed with the same
        # register_key we just generated for the RSA encryption.
        challenge = self._last_signed.challenge if self._last_signed else bytes(8)
        await self._write_chunked(build_register_root_frame(register_key, challenge))

        try:
            notif = await self._wait_for_signed(lambda n: n.notif_type == NOTIF_ROOT_KEY, timeout)
        except asyncio.TimeoutError as exc:
            raise RegistrationTimeout(
                "No ROOT_KEY notification received after REGISTER_ROOT."
            ) from exc

        root_key = derive_root_key(register_key, notif.root_key_wire)
        return Credentials(device_address=device_address, root_id=notif.root_id,
                            root_key=root_key, qr_prefix=prefix)

    async def open_channel(self, credentials: Credentials, channel: int = 1) -> None:
        """Sends a signed channel command (phase 2, e.g. open/close the gate).
        Uses the challenge from the most recently received signed notification;
        call `wait_for_any_notification()` first if none is available yet."""
        challenge = self._last_signed.challenge if self._last_signed else bytes(8)
        frame = build_switch_relais_frame(credentials.root_id, channel, credentials.root_key, challenge)
        await self._write_chunked(frame)
