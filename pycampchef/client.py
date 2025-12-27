from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional, Union

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError, BleakCharacteristicNotFoundError

from .commands import GrillCommandClient
from .const import VENDOR_CONFIGS, WsId
from .decoder import decode_notify_payload
from .models import GrillTelemetry, VendorConfig
from .discovery import uuid_for_ws

_LOGGER = logging.getLogger(__name__)


class CampChefBleClient:
    def __init__(
        self,
        address: Union[BLEDevice, str],
        *,
        vendor: Optional[VendorConfig] = None,
        notify_uuid: Optional[str] = None,
        write_uuid: Optional[str] = None,
        subscribe_ws_ids: Optional[list[int]] = None,
        extra_notify_uuids: Optional[list[str]] = None,
        on_telemetry: Optional[Callable[[GrillTelemetry], Awaitable[None]]] = None,
        bleak_client: Optional[BleakClient] = None,
    ) -> None:
        self.address = address
        self.vendor = vendor or VENDOR_CONFIGS["campchef"]
        multiplex_uuid = uuid_for_ws(WsId.MULTIPLEX, self.vendor.uuid_base_prefix)
        self.notify_uuid = notify_uuid or multiplex_uuid
        self.write_uuid = write_uuid or multiplex_uuid
        self.subscribe_ws_ids = subscribe_ws_ids
        self.extra_notify_uuids = extra_notify_uuids or []
        self._on_telemetry = on_telemetry

        self._client: Optional[BleakClient] = bleak_client
        self._notify_uuids: list[str] = []
        self._commands = GrillCommandClient(self.write_ws, self.read_ws)

    async def write_ws(self, ws_id: int, payload: bytes) -> None:
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Not connected")
        u = uuid_for_ws(ws_id, self.vendor.uuid_base_prefix)
        _LOGGER.debug("WRITE ws=0x%02X (%s) -> %s", ws_id, u, payload.hex())
        try:
            await self._client.write_gatt_char(u, payload, response=False)
            return
        except BleakError as e:
            _LOGGER.debug(
                "Write without response failed, retrying with response=True: %s", e
            )
            await self._client.write_gatt_char(u, payload, response=True)

    @property
    def commands(self) -> GrillCommandClient:
        return self._commands

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    async def connect(self, *, timeout: float = 30.0) -> None:
        if self._client and self._client.is_connected:
            return

        try:
            if self._client is None:
                self._client = BleakClient(
                    self.address, services=[self.vendor.service_uuid]
                )
            _LOGGER.info(
                "Connecting to %s",
                getattr(self.address, "address", self.address),
            )
            await self._client.connect(timeout=timeout)
        except BleakError as e:
            _LOGGER.warning("Connect/service discovery failed: %s", e)
            try:
                if self._client:
                    await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            raise

    async def start_notifications(self) -> None:
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Not connected")
        notify_uuids: list[str] = []
        for service in self._client.services:
            for ch in service.characteristics:
                if "notify" in (ch.properties or []):
                    notify_uuids.append(str(ch.uuid))
        notify_uuids.append(self.notify_uuid)
        notify_uuids.extend(self.extra_notify_uuids)
        self._notify_uuids = []
        for u in dict.fromkeys(notify_uuids):
            _LOGGER.info("Starting notifications on %s", u)
            try:
                await self._client.start_notify(u, self._handle_notify)
                self._notify_uuids.append(u)
            except BleakCharacteristicNotFoundError:
                _LOGGER.warning("Characteristic %s was not found; skipping.", u)
            except BleakError as e:
                _LOGGER.warning("Failed to enable notify on %s: %s", u, e)

    async def disconnect(self) -> None:
        if not self._client:
            return
        try:
            if self._client.is_connected:
                try:
                    await self._client.stop_notify(self.notify_uuid)
                except Exception:
                    pass
                for u in dict.fromkeys(self._notify_uuids):
                    try:
                        await self._client.stop_notify(u)
                    except Exception:
                        pass
                await self._client.disconnect()
        finally:
            self._client = None

    def list_characteristics(self) -> list[tuple[str, list[str]]]:
        if not self._client:
            return []
        try:
            services = self._client.services
        except Exception:
            return []
        if not services:
            return []
        out: list[tuple[str, list[str]]] = []
        for service in services:
            for ch in service.characteristics:
                out.append((str(ch.uuid), list(ch.properties or [])))
        return out

    async def read_ws(self, ws_id: int) -> bytes:
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Not connected")
        u = uuid_for_ws(ws_id, self.vendor.uuid_base_prefix)
        _LOGGER.debug("Reading wsId 0x%02X (%s)", ws_id, u)
        return bytes(await self._client.read_gatt_char(u))

    def _handle_notify(self, _sender: int, data: bytearray) -> None:
        raw = bytes(data)
        if not raw:
            return
        telem = decode_notify_payload(raw)
        if self._on_telemetry is not None:
            asyncio.create_task(self._on_telemetry(telem))
