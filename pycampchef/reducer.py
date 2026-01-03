# reducer.py
from __future__ import annotations

from .models import GrillState, GrillTelemetry, GrillDevice, GrillWifi, GrillStatus
from .protocol import WsId


class GrillStateReducer:
    """Merge partial GrillTelemetry updates into a coherent GrillState.

    Philosophy:
      - Prefer simple replacement for most fields.
      - Only special-case where necessary (probes, flattened convenience fields).
      - No dataclass reflection, no attribute guessing.
    """

    def __init__(self, initial: GrillState | None = None) -> None:
        self._state = initial if initial is not None else GrillState()

    @property
    def state(self) -> GrillState:
        return self._state

    def replace(self, new_state: GrillState) -> GrillState:
        self._state = new_state
        return self._state

    def reset(self) -> GrillState:
        self._state = GrillState()
        return self._state

    def apply(self, t: GrillTelemetry) -> GrillState:
        s = self._state  # alias

        # store the last raw telemetry 
        s.last_telem = t

        if t.mode is not None:
            s.mode = t.mode

        if t.chamber is not None:
            s.chamber = t.chamber

        if t.status is not None:
            s.status = merge_status(s.status, t.status)

        if t.wifi is not None:
            s.wifi = merge_wifi(s.wifi, t.wifi)

        if t.device is not None:
            s.device = merge_device(s.device, t.device)

        if t.ota is not None:
            s.ota = t.ota

        # Probes: keyed updates
        if t.probe is not None:
            idx = _probe_index(t)
            if idx is not None:
                s.probes[idx] = t.probe

        return s


def _probe_index(t: GrillTelemetry) -> int | None:
    """Infer probe index from ws_id or probe.index."""
    if t.probe is None:
        return None

    # Prefer explicit index if your GrillProbe has it
    idx = getattr(t.probe, "index", None)
    if isinstance(idx, int):
        return idx

    ws = t.ws_id
    if ws is None:
        return None

    wsv = int(ws)
    if WsId.PROBE_MIN <= wsv <= WsId.PROBE_MAX:
        return wsv - WsId.PROBE_MIN

    return None

def merge_device(current: GrillDevice | None, update: GrillDevice) -> GrillDevice:
    """Merge a partial GrillDevice update into the current GrillDevice.

    Rule: non-None fields from `update` overwrite `current`.
    """
    if current is None:
        return update

    return GrillDevice(
        info=update.info if update.info is not None else current.info,
        capabilities=update.capabilities if update.capabilities is not None else current.capabilities,
        client_secret=update.client_secret if update.client_secret is not None else current.client_secret,
        web_id=update.web_id if update.web_id is not None else current.web_id,
        http_endpoint=update.http_endpoint if update.http_endpoint is not None else current.http_endpoint,
        ws_endpoint=update.ws_endpoint if update.ws_endpoint is not None else current.ws_endpoint,
        model_fw=update.model_fw if update.model_fw is not None else current.model_fw,
        esp_fw=update.esp_fw if update.esp_fw is not None else current.esp_fw,
    )


def merge_wifi(current: GrillWifi | None, update: GrillWifi) -> GrillWifi:
    """Merge a partial GrillWifi update into the current GrillWifi."""
    if current is None:
        return update

    return GrillWifi(
        ssid=update.ssid if update.ssid is not None else current.ssid,
        status=update.status if update.status is not None else current.status,
        scanning=update.scanning if update.scanning is not None else current.scanning,
        rssi_dbm=update.rssi_dbm if update.rssi_dbm is not None else current.rssi_dbm,
    )


def merge_status(current: GrillStatus | None, update: GrillStatus) -> GrillStatus:
    """Merge a partial GrillStatus update into the current GrillStatus."""
    if current is None:
        return update

    return GrillStatus(
        transitioning=update.transitioning
        if update.transitioning is not None
        else current.transitioning,
        pellet_level=update.pellet_level
        if update.pellet_level is not None
        else current.pellet_level,
        has_fault=update.has_fault if update.has_fault is not None else current.has_fault,
    )
