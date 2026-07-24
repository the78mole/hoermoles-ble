import asyncio
import base64
import os
import struct

import hoermoles_ble.client as client_module
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from hoermoles_ble import protocol as p
from hoermoles_ble.client import HoermannClient, PropertiesRejected, RegistrationTimeout
from hoermoles_ble.credentials import Credentials
from hoermoles_ble.transport import BleTransport

# QR prefix format verified in test_protocol.py/test_qr_store.py: 9-char header + 20-digit
# serial + 2 trailing digits = 31 digits total.
_QR_PREFIX = "030202000" + "0" * 19 + "1" + "00"


class FakeTransport(BleTransport):
    """In-memory BleTransport - lets tests drive HoermannClient without real BLE hardware.
    Mirrors the pattern validated live against a real Supramatic E4 (see the scratchpad
    scripts this was adapted from)."""

    def __init__(self):
        self._callback = None
        self.written: list[bytes] = []

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def start_notify(self, callback):
        self._callback = callback

    async def stop_notify(self):
        pass

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    def notify(self, data: bytes) -> None:
        self._callback(data)


def make_signed_notification_frame(challenge: bytes, notif_type: int, payload: bytes) -> bytes:
    body = challenge + struct.pack("<H", notif_type) + b"\x00\x00" + payload
    return bytes([p.ROUTING_SIGNED]) + struct.pack("<H", len(body) + 3) + body


def make_encrypted_ack_frame(status: int) -> bytes:
    return bytes([p.ROUTING_ENCRYPTED]) + struct.pack("<H", 1 + 3) + bytes([status])


def _make_qr_text() -> tuple[str, rsa.RSAPrivateKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = private_key.public_key().public_bytes(encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo)
    return _QR_PREFIX + base64.b64encode(der).decode(), private_key


async def _enable(client: HoermannClient, transport: FakeTransport) -> None:
    transport.notify(make_signed_notification_frame(os.urandom(8), p.NOTIF_ENABLED, b""))
    await client.wait_for_any_notification(timeout=2.0)


async def test_register_success(monkeypatch):
    qr_text, _private_key = _make_qr_text()
    fixed_register_key = bytes(range(32))
    monkeypatch.setattr(client_module.secrets, "token_bytes", lambda n: fixed_register_key)

    transport = FakeTransport()
    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        device_wire_value = os.urandom(32)
        expected_root_key = p.xor_bytes(device_wire_value, fixed_register_key)

        async def responder():
            await asyncio.sleep(0.02)
            transport.notify(make_encrypted_ack_frame(p.ENCRYPTED_ACK_COMPLETE))
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            rest = struct.pack("<H", 42) + device_wire_value
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_ROOT_KEY, rest))

        asyncio.create_task(responder())
        creds = await client.register(qr_text, "AA:BB:CC:DD:EE:FF", timeout=2.0)

        assert creds.device_address == "AA:BB:CC:DD:EE:FF"
        assert creds.root_id == 42
        assert creds.root_key == expected_root_key
        assert creds.qr_prefix == _QR_PREFIX


async def test_register_raises_on_encrypted_ack_error(monkeypatch):
    qr_text, _private_key = _make_qr_text()
    monkeypatch.setattr(client_module.secrets, "token_bytes", lambda n: bytes(32))

    transport = FakeTransport()
    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder():
            await asyncio.sleep(0.02)
            transport.notify(make_encrypted_ack_frame(p.ENCRYPTED_ACK_ERROR))

        asyncio.create_task(responder())
        with pytest.raises(RegistrationTimeout):
            await client.register(qr_text, "AA:BB:CC:DD:EE:FF", timeout=2.0)


async def test_register_raises_on_root_key_timeout(monkeypatch):
    qr_text, _private_key = _make_qr_text()
    monkeypatch.setattr(client_module.secrets, "token_bytes", lambda n: bytes(32))

    transport = FakeTransport()
    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder():
            await asyncio.sleep(0.02)
            transport.notify(make_encrypted_ack_frame(p.ENCRYPTED_ACK_COMPLETE))
            # no ROOT_KEY notification ever sent

        asyncio.create_task(responder())
        with pytest.raises(RegistrationTimeout):
            await client.register(qr_text, "AA:BB:CC:DD:EE:FF", timeout=0.2)


async def test_open_channel_sends_expected_frame(monkeypatch):
    fixed_now = 1700000000
    monkeypatch.setattr(p.time, "time", lambda: fixed_now)

    root_key = os.urandom(32)
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=root_key)
    transport = FakeTransport()

    async with HoermannClient(transport) as client:
        challenge = os.urandom(8)
        transport.notify(make_signed_notification_frame(challenge, p.NOTIF_ENABLED, b""))
        await client.wait_for_any_notification(timeout=2.0)

        await client.open_channel(creds, channel=6)  # ventilation

        expected = p.build_switch_relais_frame(7, 6, root_key, challenge, now=fixed_now)
        assert b"".join(transport.written) == expected


async def test_open_channel_rejects_invalid_channel():
    transport = FakeTransport()
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=os.urandom(32))
    async with HoermannClient(transport) as client:
        with pytest.raises(ValueError):
            await client.open_channel(creds, channel=9)


async def test_read_properties_full_and_selected():
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=os.urandom(32))
    transport = FakeTransport()

    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder_full():
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            payload1 = (
                bytes([2])
                + bytes([1])
                + (0).to_bytes(2, "little", signed=True)
                + bytes([16])
                + (1).to_bytes(2, "little", signed=True)
            )
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_PROPERTIES_LIST, payload1))
            payload2 = bytes([1]) + bytes([22]) + (5).to_bytes(2, "little", signed=True)
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_PROPERTIES_LIST_END, payload2))

        asyncio.create_task(responder_full())
        result = await client.read_properties(creds, timeout=2.0)
        assert result == {1: 0, 16: 1, 22: 5}

        async def responder_selected():
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            payload = (
                bytes([2])
                + bytes([1])
                + (3).to_bytes(2, "little", signed=True)
                + bytes([16])
                + (0).to_bytes(2, "little", signed=True)
            )
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_PROPERTIES_LIST_END, payload))

        asyncio.create_task(responder_selected())
        result2 = await client.read_properties(creds, menu_groups=[1, 16], timeout=2.0)
        assert result2 == {1: 3, 16: 0}


async def test_write_properties_accepted():
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=os.urandom(32))
    transport = FakeTransport()

    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder():
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_PROPERTY_ACCEPTED, b""))

        asyncio.create_task(responder())
        await client.write_properties(creds, {16: 1}, timeout=2.0)  # must not raise


async def test_write_properties_rejected():
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=os.urandom(32))
    transport = FakeTransport()

    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder():
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_PROPERTIES_INVALID, b""))

        asyncio.create_task(responder())
        with pytest.raises(PropertiesRejected):
            await client.write_properties(creds, {16: 99}, timeout=2.0)


async def test_read_log():
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=os.urandom(32))
    transport = FakeTransport()

    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder():
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            # RELAIS entry (tag 2): causing_admin_id=1, user_id=0, otk_id=0, toggled_channel=1
            relais_data = (1).to_bytes(2, "little") + bytes([0]) + (0).to_bytes(2, "little") + bytes([1])
            ts = 12345
            payload1 = bytes([len(relais_data), 2]) + struct.pack("<I", ts) + relais_data
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_LOG, payload1))

            # EXECUTED_ADMIN_ACTION entry (tag 6): causing_admin_id=1, action=CHANNEL_1 (0x11)
            action_data = (1).to_bytes(2, "little") + (0x11).to_bytes(2, "little")
            payload2 = bytes([len(action_data), 6]) + struct.pack("<I", ts + 10) + action_data
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_LOG_END, payload2))

        asyncio.create_task(responder())
        entries = await client.read_log(creds, timeout=2.0)

        assert len(entries) == 2
        assert entries[0][0] == 2
        assert entries[1][0] == 6


async def test_read_service_data():
    creds = Credentials(device_address="AA:BB:CC:DD:EE:FF", root_id=7, root_key=os.urandom(32))
    transport = FakeTransport()

    async with HoermannClient(transport) as client:
        await _enable(client, transport)

        async def responder():
            await asyncio.sleep(0.02)
            chal = client._last_signed.challenge
            payload1 = bytes([2]) + struct.pack("<I", 1234) + bytes([1]) + struct.pack("<I", 99) + bytes([0])
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_SERVICE_DATA, payload1))
            payload2 = bytes([1]) + struct.pack("<I", 5555) + bytes([7])
            transport.notify(make_signed_notification_frame(chal, p.NOTIF_SERVICE_DATA_END, payload2))

        asyncio.create_task(responder())
        result = await client.read_service_data(creds, timeout=2.0)
        assert result == {1: 1234, 0: 99, 7: 5555}
