from __future__ import annotations

from typing import Optional
from .const import WsId

GRILL_OTA_WSIDS: set[WsId] = {
    WsId.OTA_STATE
}

DEVICE_INFO_WSIDS: set[WsId] = {
    WsId.DEVICE_INFO,
    WsId.CLIENT_SECRET,
    WsId.WEB_ID,
    WsId.HTTP_ENDPOINT,
    WsId.WS_ENDPOINT,
    WsId.MODEL_FW,
    WsId.ESP_FW,
}

GRILL_STATUS_WSIDS: set[WsId] = {
    WsId.TRANSITIONING,
    WsId.PELLET_LEVEL,
    WsId.LAST_FAULT
}

GRILL_WIFI_WSIDS: set[WsId] = {
    WsId.WIFI_RSSI,
    WsId.WIFI_SCANNING,
    WsId.WIFI_SSID,
    WsId.WIFI_STATUS
}

POLL_WSIDS: set[WsId] = {
    WsId.MODE,
    WsId.CHAMBER_TEMP,
} | GRILL_STATUS_WSIDS | GRILL_WIFI_WSIDS | GRILL_OTA_WSIDS


def encode_mode_payload(
    mode_code: int,
    *,
    set_temp_f: Optional[int] = None,
    smoke_level: Optional[int] = None,
    fan_level: Optional[int] = None,
    extra: bytes = b"",
) -> bytes:
    data = bytearray([mode_code])
    if mode_code == 0x11:
        if set_temp_f is None or smoke_level is None:
            raise ValueError("set_temp_f and smoke_level are required for RUN mode")
        data += int(set_temp_f).to_bytes(2, byteorder="big", signed=True)
        data.append(int(smoke_level) & 0xFF)
    elif mode_code == 0x01:
        if fan_level is None:
            raise ValueError("fan_level is required for FAN mode")
        data.append(int(fan_level) & 0xFF)
    data += extra
    return bytes(data)
