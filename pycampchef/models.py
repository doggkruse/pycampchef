from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .const import ModeName, OtaState, WifiStatus, WsId

@dataclass(frozen=True)
class VendorConfig:
    name: str
    adv_name_prefix: str
    service_uuid: str
    uuid_base_prefix: str


@dataclass(frozen=True)
class GrillProbe:
    index: int
    i16: int
    connected: bool
    temp_f: Optional[float] = None


@dataclass(frozen=True)
class GrillChamber:
    i16: int
    temp_f: float


@dataclass(frozen=True)
class GrillMode:
    mode: Optional["ModeName"] = None
    set_temp_f: Optional[int] = None
    smoke_level: Optional[int] = None
    fan_level: Optional[int] = None


@dataclass(frozen=True)
class GrillStatus:
    transitioning: Optional[bool] = None
    pellet_level: Optional[int] = None
    has_fault: Optional[bool] = None


@dataclass(frozen=True)
class GrillWifi:
    ssid: Optional[str] = None
    status: Optional["WifiStatus"] = None
    scanning: Optional[bool] = None
    rssi_dbm: Optional[int] = None


@dataclass(frozen=True)
class GrillDevice:
    info: Optional["DeviceInfo"] = None
    capabilities: Optional["ModelCapabilities"] = None
    client_secret: Optional[str] = None
    web_id: Optional[str] = None
    http_endpoint: Optional[str] = None
    ws_endpoint: Optional[str] = None
    model_fw: Optional[str] = None
    esp_fw: Optional[str] = None


@dataclass(frozen=True)
class GrillOta:
    state: Optional["OtaState"] = None
    progress_percent: Optional[int] = None


@dataclass(frozen=True)
class GrillTelemetry:
    # If message is wsId-prefixed, ws_id is that first byte.
    ws_id: Optional["WsId | int"] = None

    probe: Optional[GrillProbe] = None
    chamber: Optional[GrillChamber] = None
    mode: Optional[GrillMode] = None
    status: Optional[GrillStatus] = None
    wifi: Optional[GrillWifi] = None
    device: Optional[GrillDevice] = None
    ota: Optional[GrillOta] = None

    # Raw bytes
    raw: bytes = b""


@dataclass(frozen=True)
class DeviceInfo:
    model_id: str
    capability_flags: int
    max_grill_temp_f: int


@dataclass(frozen=True)
class ModelCapabilities:
    capabilities_known: bool
    probe_count: Optional[int]
    sku: Optional[str]
    min_temp_f: Optional[int]
    spec_max_temp_f: Optional[int]
    smoke_threshold_f: Optional[int]
    high_temp_threshold_f: Optional[int]
    low_smoke_write_command: Optional[int]
    high_smoke_write_command: Optional[int]
    has_high_temp_setting: Optional[bool]
    has_night_mode: Optional[bool]
    max_temp_f: Optional[int]


@dataclass(slots=True)
class GrillState:
    mode: Optional[GrillMode] = None
    chamber: Optional[GrillChamber] = None
    status: Optional[GrillStatus] = None
    wifi: Optional[GrillWifi] = None
    device: Optional[GrillDevice] = None
    ota: Optional[GrillOta] = None
    probes: dict[int, GrillProbe] = field(default_factory=dict)
    model: str | None = None
    last_telem: Optional[GrillTelemetry] = None
