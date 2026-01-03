from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .decoder import decode_notify_payload
from .discovery import uuid_for_ws
from .models import GrillState
from .protocol import POLL_WSIDS, DEVICE_INFO_WSIDS
from .const import WsId
from .reducer import GrillStateReducer
from .commands import GrillCommandClient

from bleak import BleakClient, BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakConnectionError,
    establish_connection,
)

_LOGGER = logging.getLogger(__name__)

class CampChefBleClient:
    """Low-level Camp Chef BLE client.

    Owns:
      - BLE connection lifecycle
      - Notification enablement + handling
      - Snapshot reads
      - Internal state cache
    """

    def __init__(
        self,
        address: str,
        vendor: str,
        *,
        on_update: Callable[[Grillstate], None] | None = None,
        bleak_client: Optional[BleakClient] = None,
    ) -> None:
        self._address = address
        self._on_update = on_update

        self._reducer = GrillStateReducer()
        self._notifications_active = False
        self._vendor = vendor

        # BLE client / transport
        self._bleak_client: Optional[BleakClient] = bleak_client
        self._commands = GrillCommandClient(self._write_ws, self._read_ws)


    # -----------------
    # Properties
    # -----------------

    @property
    def state(self) -> GrillState:
        return self._reducer.state

    @property
    def commands(self) -> GrillCommandClient:
        return self._commands

    @property
    def is_connected(self) -> bool:
        return bool(self._bleak_client and self._bleak_client.is_connected)

    @property
    def is_notifying(self) -> bool:
        return self._notifications_active

    # -----------------
    # Public API
    # -----------------

    async def ensure_connected(self) -> None:
        """Ensure the BLE device is connected and ready.

        Placeholder:
          - Discover device
          - Connect
          - Pair if required
          - Prepare GATT client
        """
        if self.is_connected:
            return

        try:
            _LOGGER.info(
                "Connecting to %s",
                getattr(self._address, "address"),
            )
            if self.is_connected:
                await self.disconnect()
            self._bleak_client = await establish_connection(
                BleakClientWithServiceCache,
                self._address,
                __name__,
                disconnected_callback=self._handle_disconnect,
            )
            # must be BLE paired to read / write but no passcode required
            try:
                await self._bleak_client.pair()
            except (NotImplementedError, BleakError) as e:
                msg = str(e).lower()
                if isinstance(e, NotImplementedError) or "not supported" in msg or "not available" in msg:
                    _LOGGER.debug(
                        "BLE pairing not available; continuing without pairing: %s",
                        e,
                    )
                else:
                    raise

            # if a notification callback was provided, enable notifications
            if self._on_update:
                await self._start_notifications()

        except BleakError as e:
            _LOGGER.warning("Connect/service discovery failed: %s", e)
            await self.disconnect()
            self._bleak_client = None
            raise

    async def get_state_snapshot(self) -> GrillState:
        """Perform a full (polling) snapshot read of device state.
        """
        device = getattr(self._reducer.state, "device", None)
        if device is None or device.info is None:
            await self._read_wsids(DEVICE_INFO_WSIDS)

        # characteristic reads + decoding
        await self._read_wsids(POLL_WSIDS)

        # sample the probes, assumes there's at least one
        caps = getattr(self._reducer.state.device, "capabilities", None)
        probe_count = getattr(caps, "probe_count", None) or 1

        await self._read_wsids(
            range(WsId.PROBE_MIN, WsId.PROBE_MIN + probe_count)
        )

        return self.state

    async def disconnect(self) -> None:
        """Disconnect from the BLE device."""
        if self.is_connected:
            try:
                await self._bleak_client.disconnect()
            except Exception:
                pass
        self._notifications_active = False
        self._bleak_client = None

    # -----------------
    # Internal helpers
    # -----------------

    async def _start_notifications(self) -> None:
        try:
            await self._bleak_client.start_notify(uuid_for_ws(WsId.MULTIPLEX, self._vendor.uuid_base_prefix), self._handle_notify)
            self._notifications_active = True
        except Exception as e:
            _LOGGER.warning("Enabling notifications failed: %s", e)
            self._notifications_active = False
            return False
        return self._notifications_active

    async def _read_wsids(self, wsids: [WsId]) -> None:
        for ws_id in wsids:
            try:
                raw = await self._read_ws(ws_id)
            except Exception as exc:
                print(f"read ws=0x{ws_id:02x} error={exc}")
                if self.is_connected:
                    await self.disconnect()
                break
            if not raw:
                print(f"read ws=0x{ws_id:02x} empty")
                continue
            telem = decode_notify_payload(bytes([ws_id]) + raw)
            print(f"telem={telem}\n")
            self._reducer.apply(telem)

    async def _read_ws(self, ws_id: int) -> bytes:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        u = uuid_for_ws(ws_id, self._vendor.uuid_base_prefix)
        _LOGGER.debug("Reading wsId 0x%02X (%s)", ws_id, u)
        return bytes(await self._bleak_client.read_gatt_char(u, timeout=5))

    async def _write_ws(self, ws_id: int, payload: bytes) -> None:
        if not self.is_connected:
            raise RuntimeError("Not connected")
        u = uuid_for_ws(ws_id, self._vendor.uuid_base_prefix)
        _LOGGER.debug("WRITE ws=0x%02X (%s) -> %s", ws_id, u, payload.hex())
        try:
            await self._bleak_client.write_gatt_char(u, payload, response=False)
            return
        except BleakError as e:
            _LOGGER.debug(
                "Write without response failed, retrying with response=True: %s", e
            )
            await self._bleak_client.write_gatt_char(u, payload, response=True)

    def _handle_notify(self, _sender: int, data: bytearray) -> None:
        raw = bytes(data)
        if not raw:
            return
        telem = decode_notify_payload(raw)
        self._reducer.apply(telem)
        if self._on_update is not None:
            asyncio.create_task(self._on_update(self.state))

    def _handle_disconnect(self, _client) -> None:
        self._bleak_client = None
        _LOGGER.debug("BLE device disconnected")
