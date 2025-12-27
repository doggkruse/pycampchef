from __future__ import annotations

"""Public package API for pycampchef.

Prefer importing from this package root instead of module-level files.
"""

import logging

from .client import CampChefBleClient
from .discovery import async_discover
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

__all__ = [
    "CampChefBleClient",
    "GrillChamber",
    "DeviceInfo",
    "GrillDevice",
    "GrillMode",
    "GrillOta",
    "GrillProbe",
    "GrillStatus",
    "GrillTelemetry",
    "ModelCapabilities",
    "GrillWifi",
    "async_discover",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
