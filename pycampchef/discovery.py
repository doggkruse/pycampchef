from __future__ import annotations

from typing import Optional

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from .const import VENDOR_CONFIGS
from .models import VendorConfig


def uuid_for_ws(ws_id: int, uuid_base_prefix: str) -> str:
    if not (0 <= ws_id <= 0xFF):
        raise ValueError("ws_id must be 0..255")
    return f"{uuid_base_prefix}{ws_id:02x}"


def infer_vendor_from_name(name: str) -> Optional[VendorConfig]:
    for cfg in VENDOR_CONFIGS.values():
        if name.startswith(cfg.adv_name_prefix):
            return cfg
    return None


def infer_vendor_from_services(uuids: Optional[list[str]]) -> Optional[VendorConfig]:
    if not uuids:
        return None
    norm = {u.lower() for u in uuids}
    for key in ("campchef", "cabelas", "kingsford"):
        cfg = VENDOR_CONFIGS[key]
        if cfg.service_uuid.lower() in norm:
            return cfg
    return None


async def async_discover(
    timeout: float = 8.0,
) -> list[tuple[BLEDevice, str, VendorConfig]]:
    """Returns [(ble_device, name, vendor)] for supported devices."""
    devices = await BleakScanner.discover(timeout=timeout)
    out: list[tuple[BLEDevice, str, VendorConfig]] = []
    for d in devices:
        name = d.name or ""
        cfg = infer_vendor_from_name(name)
        if cfg is None:
            details = getattr(d, "details", None)
            uuids = None
            if isinstance(details, dict):
                uuids = details.get("uuids")
            cfg = infer_vendor_from_services(uuids)
        if cfg is not None:
            out.append((d, name, cfg))
    return out
