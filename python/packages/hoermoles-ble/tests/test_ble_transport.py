"""Tests for the bleak transport's two modes (address vs. injected client).

No real BLE: a FakeBleakClient records the calls. The injected-client mode is what
the Home Assistant integration uses - it hands in a client from
bleak_retry_connector.establish_connection() (already connected), so connect()
must not connect again and disconnect() must not drop the caller-owned client.
"""

import hoermoles_ble.ble_transport as ble_transport_module
import pytest
from hoermoles_ble.ble_transport import BleakTransport
from hoermoles_ble.protocol import BC_RX, BC_TX


class FakeBleakClient:
    def __init__(self, address="AA:BB:CC:DD:EE:FF", *, connected=False, **kwargs):
        self.address = address
        self.is_connected = connected
        self.mtu_size = 247
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.written: list[tuple[str, bytes, bool]] = []
        self.notify_char: str | None = None
        self.stop_notify_char: str | None = None

    async def connect(self):
        self.connect_calls += 1
        self.is_connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False

    async def write_gatt_char(self, char, data, response=True):
        self.written.append((char, bytes(data), response))

    async def start_notify(self, char, callback):
        self.notify_char = char
        self._callback = callback

    async def stop_notify(self, char):
        self.stop_notify_char = char


def test_requires_address_or_client():
    with pytest.raises(ValueError):
        BleakTransport()


async def test_address_mode_owns_and_drops_client(monkeypatch):
    created: list[FakeBleakClient] = []

    def _factory(address, adapter=None, disconnected_callback=None):
        client = FakeBleakClient(address)
        created.append(client)
        return client

    monkeypatch.setattr(ble_transport_module, "BleakClient", _factory)

    transport = BleakTransport("AA:BB:CC:DD:EE:FF")
    await transport.connect()
    assert created and created[0].connect_calls == 1

    await transport.write(b"\x01\x02")
    assert created[0].written == [(BC_TX, b"\x01\x02", False)]  # Write Without Response

    await transport.disconnect()
    assert created[0].disconnect_calls == 1
    # address mode drops its owned client so a fresh connect rebuilds one
    assert transport._client is None


async def test_injected_already_connected_client_not_reconnected():
    client = FakeBleakClient(connected=True)
    transport = BleakTransport.from_client(client)

    await transport.connect()
    assert client.connect_calls == 0  # establish_connection already connected it

    received: list[bytes] = []
    await transport.start_notify(received.append)
    assert client.notify_char == BC_RX

    await transport.disconnect()
    assert client.disconnect_calls == 1
    # injected client stays referenced - the caller owns its lifecycle
    assert transport._client is client


async def test_injected_disconnected_client_gets_connected():
    client = FakeBleakClient(connected=False)
    transport = BleakTransport(client=client)

    await transport.connect()
    assert client.connect_calls == 1


async def test_start_notify_wraps_bytearray():
    client = FakeBleakClient(connected=True)
    transport = BleakTransport(client=client)
    await transport.connect()

    received: list[bytes] = []
    await transport.start_notify(received.append)
    client._callback(None, bytearray(b"\xaa\xbb"))
    assert received == [b"\xaa\xbb"]
    assert isinstance(received[0], bytes)
