"""
Abstract transport interface. HoermannClient (client.py) only knows this
interface, not bleak/BlueZ directly - a port to a different BLE stack (e.g.
NimBLE/Zephyr on a microcontroller) only needs to reimplement these four
methods; the whole protocol flow in client.py stays the same.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class BleTransport(ABC):
    """A connected GATT channel to exactly one Hoermann BlueSecur drive."""

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def write(self, data: bytes) -> None:
        """Writes <= GATT_WRITE_CHUNK_SIZE bytes to the TX characteristic
        (Write Without Response - see the protocol.py module docstring)."""

    @abstractmethod
    async def start_notify(self, callback: Callable[[bytes], None]) -> None:
        """Subscribes to notifications on the RX characteristic."""

    @abstractmethod
    async def stop_notify(self) -> None:
        ...

    async def __aenter__(self) -> "BleTransport":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.disconnect()
