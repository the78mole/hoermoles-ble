"""bleak-based BleTransport implementation (Linux/BlueZ, macOS, Windows)."""

from __future__ import annotations

from collections.abc import Callable

from bleak import BleakClient

from .protocol import BC_RX, BC_TX
from .transport import BleTransport


class BleakTransport(BleTransport):
    """bleak transport in one of two modes:

    - *address mode* (the CLI's case): pass an `address` and this class builds and
      owns the `BleakClient`, connecting it in `connect()` and disconnecting +
      dropping it in `disconnect()`.
    - *injected-client mode* (the Home Assistant integration's case): pass an
      existing `client` - e.g. one returned already-connected by
      `bleak_retry_connector.establish_connection()` using a BLEDevice from Home
      Assistant's shared Bluetooth stack. `connect()` then only connects it if it
      isn't already; the caller keeps ownership of the client object. This keeps
      `bleak-retry-connector`/`habluetooth` out of this core library - the HA glue
      lives in the HA integration and only hands us a ready client.
    """

    def __init__(
        self,
        address: str | None = None,
        adapter: str | None = None,
        on_log: Callable[[str], None] | None = None,
        *,
        client: BleakClient | None = None,
    ):
        if client is None and address is None:
            raise ValueError("BleakTransport needs either an address or an existing client")
        self._address = address
        self._adapter = adapter
        self._on_log = on_log or (lambda msg: None)
        self._client: BleakClient | None = client
        self._owns_client = client is None

    @classmethod
    def from_client(cls, client: BleakClient, on_log: Callable[[str], None] | None = None) -> BleakTransport:
        """Wrap an already-obtained (typically already-connected) BleakClient -
        the injected-client mode described in the class docstring."""
        return cls(client=client, on_log=on_log)

    def _on_disconnected(self, client: BleakClient) -> None:
        self._on_log(f"BLE connection lost (disconnected_callback), was connected={client.is_connected}")

    async def connect(self) -> None:
        if self._client is None:
            self._client = BleakClient(
                self._address, adapter=self._adapter, disconnected_callback=self._on_disconnected
            )
        if not self._client.is_connected:
            await self._client.connect()
        self._on_log(f"MTU after connecting: {self._client.mtu_size}")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            # An injected client is owned by the caller (e.g. the HA connection
            # helper managing the connection-slot lifecycle) - disconnect it, but
            # keep the reference rather than dropping it.
            if self._owns_client:
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
