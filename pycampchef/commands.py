from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from .const import WifiStatus, WsId
from .decoder import decode_notify_payload
from .models import GrillMode, GrillTelemetry
from .protocol import encode_mode_payload

_LOGGER = logging.getLogger(__name__)


@dataclass
class GrillCommandClient:
    write_ws: Callable[[int, bytes], Awaitable[None]]
    read_ws: Callable[[int], Awaitable[bytes]]

    async def set_temp_smoke(self, temp_f: int, smoke_level: int) -> None:
        _LOGGER.info(
            "Sending mode RUN temp_f=%d smoke=%d (wsId 0x01)", temp_f, smoke_level
        )
        payload = encode_mode_payload(0x11, set_temp_f=temp_f, smoke_level=smoke_level)
        await self.write_ws(WsId.MODE, payload)

    async def set_fan(self, fan_level: int) -> None:
        _LOGGER.info("Sending mode FAN fan=%d (wsId 0x01)", fan_level)
        payload = encode_mode_payload(0x01, fan_level=fan_level)
        await self.write_ws(WsId.MODE, payload)

    async def wifi_ssid(self, ssid: str) -> None:
        _LOGGER.info("Sending Wi-Fi SSID (wsId 0x20)")
        await self.write_ws(WsId.WIFI_SSID, ssid.encode("utf-8"))

    async def wifi_password(self, password: str) -> None:
        _LOGGER.info("Sending Wi-Fi password (wsId 0x21)")
        await self.write_ws(WsId.WIFI_PASSWORD, password.encode("utf-8"))

    async def wait_wifi_connection_status(
        self, *, timeout: float = 60.0, interval: float = 1.0
    ) -> GrillTelemetry:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            raw = await self.read_ws(WsId.WIFI_STATUS)
            telem = decode_notify_payload(bytes([WsId.WIFI_STATUS]) + raw)
            wifi = getattr(telem, "wifi", None)
            if wifi and wifi.status is not None:
                _LOGGER.info("Wi-Fi connection status: %s", wifi.status)
                if wifi.status in (WifiStatus.CONNECTED, WifiStatus.ERROR):
                    return telem
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Wi-Fi connection status timed out")
            await asyncio.sleep(min(interval, remaining))

    async def wifi_credentials(
        self,
        ssid: str,
        password: str,
        *,
        status_timeout: float = 60.0,
    ) -> GrillTelemetry:
        _LOGGER.info("Provisioning Wi-Fi credentials")
        await self.write_ws(WsId.WIFI_SSID, ssid.encode("utf-8"))
        await asyncio.sleep(0.5)
        await self.write_ws(WsId.WIFI_PASSWORD, password.encode("utf-8"))
        await asyncio.sleep(5.0)
        return await self.wait_wifi_connection_status(timeout=status_timeout)

    async def wifi_scan(self, enabled: bool) -> None:
        payload = bytes([1 if enabled else 0])
        _LOGGER.info("Sending Wi-Fi scan %s (wsId 0x23)", "start" if enabled else "stop")
        await self.write_ws(WsId.WIFI_SCANNING, payload)
        if enabled:
            await asyncio.sleep(0.5)
            raw = await self.read_ws(WsId.WIFI_SCANNING)
            telem = decode_notify_payload(bytes([WsId.WIFI_SCANNING]) + raw)
            wifi = getattr(telem, "wifi", None)
            if wifi and wifi.scanning is False:
                _LOGGER.warning("Wi-Fi scan did not start yet (wsId 0x23 readback false)")

    async def wait_wifi_scan_complete(
        self, *, timeout: float = 60.0, interval: float = 1.0
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        saw_scanning = False
        while True:
            raw = await self.read_ws(WsId.WIFI_SCANNING)
            telem = decode_notify_payload(bytes([WsId.WIFI_SCANNING]) + raw)
            wifi = getattr(telem, "wifi", None)
            scanning = wifi.scanning if wifi else None
            if scanning is True:
                saw_scanning = True
            if saw_scanning and scanning is False:
                return
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Wi-Fi scan did not finish before timeout")
            await asyncio.sleep(min(interval, remaining))

    async def read_mode(self) -> GrillMode:
        raw = await self.read_ws(WsId.MODE)
        telem = decode_notify_payload(bytes([WsId.MODE]) + raw)
        mode = telem.mode
        if mode is None:
            raise RuntimeError("Mode characteristic not available")
        return mode

    async def read_firmware_string(self) -> Optional[str]:
        try:
            raw = await self.read_ws(WsId.MODEL_FW)
        except Exception as exc:
            _LOGGER.debug("Firmware read failed: %s", exc)
            return None
        s = raw.decode("utf-8", errors="ignore").strip("\x00").strip()
        return s or None
