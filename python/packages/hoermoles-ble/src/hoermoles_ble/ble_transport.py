"""bleak-based BleTransport implementation (Linux/BlueZ, macOS, Windows)."""

from __future__ import annotations

from collections.abc import Callable

from bleak import BleakClient

from .protocol import BC_RX, BC_TX
from .transport import BleTransport


class BleakTransport(BleTransport):
    def __init__(self, address: str, adapter: str | None = None, on_log: Callable[[str], None] | None = None):
        self._address = address
        self._adapter = adapter
        self._on_log = on_log or (lambda msg: None)
        self._client: BleakClient | None = None

    def _on_disconnected(self, client: BleakClient) -> None:
        self._on_log(f"BLE connection lost (disconnected_callback), was connected={client.is_connected}")

    async def connect(self) -> None:
        self._client = BleakClient(self._address, adapter=self._adapter, disconnected_callback=self._on_disconnected)
        await self._client.connect()
        self._on_log(f"MTU after connecting: {self._client.mtu_size}")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def write(self, data: bytes) -> None:
        assert self._client is not None, "not connected"
        self._on_log(f"  write_gatt_char {len(data)} bytes: {data.hex()} (is_connected={self._client.is_connected})")
        await self._client.write_gatt_char(BC_TX, data, response=False)

    async def start_notify(self, callback: Callable[[bytes], None]) -> None:
        assert self._client is not None, "not connected"

        def _on_notify(_, data: bytearray) -> None:
            callback(bytes(data))

        await self._client.start_notify(BC_RX, _on_notify)

    async def stop_notify(self) -> None:
        if self._client is not None:
            await self._client.stop_notify(BC_RX)
