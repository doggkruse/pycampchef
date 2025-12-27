from __future__ import annotations

from typing import Optional

from .const import ModeName, OtaState, WifiStatus, WsId
from .models import (
    DeviceInfo,
    GrillChamber,
    GrillDevice,
    GrillMode,
    GrillOta,
    GrillProbe,
    GrillStatus,
    GrillTelemetry,
    GrillWifi,
    ModelCapabilities,
)


def _derive_capabilities(info: DeviceInfo) -> ModelCapabilities:
    model_id = info.model_id
    max_temp = info.max_grill_temp_f
    if model_id == "CPPG":
        spec_max = 500
        return ModelCapabilities(
            capabilities_known=True,
            probe_count=4,
            sku="PG20CT",
            min_temp_f=160,
            spec_max_temp_f=spec_max,
            smoke_threshold_f=350,
            high_temp_threshold_f=450,
            low_smoke_write_command=150,
            high_smoke_write_command=155,
            has_high_temp_setting=True,
            has_night_mode=True,
            max_temp_f=max_temp or spec_max,
        )
    if model_id == "CDLX":
        spec_max = 500
        return ModelCapabilities(
            capabilities_known=True,
            probe_count=4,
            sku="N/A",
            min_temp_f=160,
            spec_max_temp_f=spec_max,
            smoke_threshold_f=350,
            high_temp_threshold_f=450,
            low_smoke_write_command=150,
            high_smoke_write_command=155,
            has_high_temp_setting=True,
            has_night_mode=True,
            max_temp_f=max_temp or spec_max,
        )
    if model_id == "CXXL":
        spec_max = 350
        return ModelCapabilities(
            capabilities_known=True,
            probe_count=4,
            sku="PGVXXL",
            min_temp_f=150,
            spec_max_temp_f=spec_max,
            smoke_threshold_f=350,
            high_temp_threshold_f=350,
            low_smoke_write_command=140,
            high_smoke_write_command=145,
            has_high_temp_setting=False,
            has_night_mode=True,
            max_temp_f=max_temp or spec_max,
        )
    if model_id in {"F0YW", "F1YW"}:
        spec_max = 500
        return ModelCapabilities(
            capabilities_known=True,
            probe_count=2,
            sku="PGVXXL",
            min_temp_f=160,
            spec_max_temp_f=spec_max,
            smoke_threshold_f=350,
            high_temp_threshold_f=450,
            low_smoke_write_command=150,
            high_smoke_write_command=155,
            has_high_temp_setting=True,
            has_night_mode=False,
            max_temp_f=max_temp or spec_max,
        )
    if model_id == "F3YW":
        spec_max = 350
        return ModelCapabilities(
            capabilities_known=True,
            probe_count=2,
            sku="PGVXXL",
            min_temp_f=150,
            spec_max_temp_f=spec_max,
            smoke_threshold_f=350,
            high_temp_threshold_f=350,
            low_smoke_write_command=140,
            high_smoke_write_command=145,
            has_high_temp_setting=False,
            has_night_mode=False,
            max_temp_f=max_temp or spec_max,
        )
    return ModelCapabilities(
        capabilities_known=False,
        probe_count=0,
        sku=None,
        min_temp_f=None,
        spec_max_temp_f=None,
        smoke_threshold_f=None,
        high_temp_threshold_f=None,
        low_smoke_write_command=None,
        high_smoke_write_command=None,
        has_high_temp_setting=None,
        has_night_mode=None,
        max_temp_f=max_temp,
    )


def _decode_i16_le(payload: bytes) -> int:
    if len(payload) < 2:
        raise ValueError("need at least 2 bytes")
    return int.from_bytes(payload[:2], byteorder="little", signed=True)


def _decode_i16_be(payload: bytes) -> int:
    if len(payload) < 2:
        raise ValueError("need at least 2 bytes")
    return int.from_bytes(payload[:2], byteorder="big", signed=True)


def _decode_i8(payload: bytes) -> int:
    if len(payload) < 1:
        raise ValueError("need at least 1 byte")
    return int.from_bytes(payload[:1], byteorder="little", signed=True)


def _probe_i16_to_f(i16: int) -> Optional[float]:
    # Probe is DegreesFahrenheit stored as an i16.
    if i16 == 0:
        return None
    if -40 <= i16 <= 700:
        return float(i16)
    return None


def _chamber_i16_to_f(i16: int) -> float:
    # Chamber is Q8.8 fixed-point °F.
    return i16 / 256.0


def decode_notify_payload(raw: bytes) -> GrillTelemetry:
    if not raw:
        return GrillTelemetry(raw=raw)

    # wsId-prefixed multiplex: [wsId][payload...]
    raw_ws_id = raw[0]
    try:
        ws_id = WsId(raw_ws_id)
    except ValueError:
        ws_id = raw_ws_id
    payload = raw[1:]

    telem = GrillTelemetry(ws_id=ws_id, raw=raw)

    if ws_id == WsId.CHAMBER_TEMP and len(payload) >= 2:
        try:
            v = _decode_i16_le(payload)
            return GrillTelemetry(
                ws_id=ws_id,
                chamber=GrillChamber(i16=v, temp_f=_chamber_i16_to_f(v)),
                raw=raw,
            )
        except Exception:
            return telem

    if WsId.PROBE_MIN <= ws_id <= WsId.PROBE_MAX and len(payload) >= 2:
        try:
            v = _decode_i16_be(payload)
            idx = int(ws_id - WsId.PROBE_MIN)
            connected = v != 0
            return GrillTelemetry(
                ws_id=ws_id,
                probe=GrillProbe(
                    index=idx,
                    i16=v,
                    connected=connected,
                    temp_f=_probe_i16_to_f(v),
                ),
                raw=raw,
            )
        except Exception:
            return telem

    if ws_id == WsId.WIFI_RSSI and len(payload) >= 1:
        try:
            rssi = _decode_i8(payload)
            return GrillTelemetry(
                ws_id=ws_id,
                wifi=GrillWifi(rssi_dbm=rssi),
                raw=raw,
            )
        except Exception:
            return telem

    if ws_id == WsId.MODE:
        if not payload:
            return GrillTelemetry(
                ws_id=ws_id,
                mode=GrillMode(mode=None),
                raw=raw,
            )
        mode_code = payload[0]
        try:
            mode_name = ModeName(mode_code)
        except ValueError:
            mode_name = None
        set_temp = None
        smoke = None
        fan = None
        if mode_code == 0x11 and len(payload) >= 4:
            try:
                set_temp = int.from_bytes(payload[1:3], byteorder="big", signed=True)
                smoke = payload[3]
            except Exception:
                set_temp = None
                smoke = None
        elif mode_code == 0x01 and len(payload) >= 2:
            fan = payload[1]
        return GrillTelemetry(
            ws_id=ws_id,
            mode=GrillMode(
                mode=mode_name,
                set_temp_f=set_temp,
                smoke_level=smoke,
                fan_level=fan,
            ),
            raw=raw,
        )

    if ws_id == WsId.TRANSITIONING and len(payload) >= 1:
        transitioning = payload[0] != 0
        return GrillTelemetry(
            ws_id=ws_id,
            status=GrillStatus(transitioning=transitioning),
            raw=raw,
        )

    if ws_id == WsId.PELLET_LEVEL and len(payload) >= 1:
        pellet = payload[0]
        return GrillTelemetry(
            ws_id=ws_id,
            status=GrillStatus(pellet_level=pellet),
            raw=raw,
        )

    if ws_id == WsId.LAST_FAULT and payload:
        has_fault = any(b != 0 for b in payload)
        return GrillTelemetry(
            ws_id=ws_id,
            status=GrillStatus(
                has_fault=has_fault,
            ),
            raw=raw,
        )

    if ws_id == WsId.DEVICE_INFO and payload:
        if len(payload) >= 8:
            model_id = payload[0:4].decode("ascii", errors="ignore").strip("\x00").strip()
            capability_flags = int.from_bytes(payload[4:6], byteorder="big", signed=False)
            max_grill_temp_f = int.from_bytes(payload[6:8], byteorder="big", signed=False)
            info = DeviceInfo(
                model_id=model_id,
                capability_flags=capability_flags,
                max_grill_temp_f=max_grill_temp_f,
            )
            caps = _derive_capabilities(info)
            return GrillTelemetry(
                ws_id=ws_id,
                device=GrillDevice(
                    info=info,
                    capabilities=caps,
                ),
                raw=raw,
            )
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(),
            raw=raw,
        )

    if ws_id == WsId.CLIENT_SECRET and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(client_secret=s or None),
            raw=raw,
        )

    if ws_id == WsId.WEB_ID and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        if not s:
            s = payload.hex()
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(web_id=s),
            raw=raw,
        )

    if ws_id == WsId.HTTP_ENDPOINT and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(http_endpoint=s or None),
            raw=raw,
        )

    if ws_id == WsId.WS_ENDPOINT and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(ws_endpoint=s or None),
            raw=raw,
        )

    if ws_id == WsId.WIFI_SSID and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        return GrillTelemetry(
            ws_id=ws_id,
            wifi=GrillWifi(ssid=s or None),
            raw=raw,
        )

    if ws_id == WsId.WIFI_STATUS and len(payload) >= 1:
        raw_status = payload[0]
        try:
            status = WifiStatus(raw_status)
        except ValueError:
            status = None
        return GrillTelemetry(
            ws_id=ws_id,
            wifi=GrillWifi(status=status),
            raw=raw,
        )

    if ws_id == WsId.WIFI_SCANNING and len(payload) >= 1:
        return GrillTelemetry(
            ws_id=ws_id,
            wifi=GrillWifi(scanning=(payload[0] != 0)),
            raw=raw,
        )

    if ws_id == WsId.MODEL_FW and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(model_fw=s or None),
            raw=raw,
        )

    if ws_id == WsId.ESP_FW and payload:
        s = payload.decode("utf-8", errors="ignore").strip("\x00").strip()
        return GrillTelemetry(
            ws_id=ws_id,
            device=GrillDevice(esp_fw=s or None),
            raw=raw,
        )

    if ws_id == WsId.OTA_STATE and len(payload) >= 1:
        v = payload[0]
        if v == 0:
            state = OtaState.IDLE
            progress = None
        elif 1 <= v <= 100:
            state = OtaState.IN_PROGRESS
            progress = v
        else:
            state = OtaState.UNKNOWN
            progress = None
        return GrillTelemetry(
            ws_id=ws_id,
            ota=GrillOta(state=state, progress_percent=progress),
            raw=raw,
        )

    return telem
