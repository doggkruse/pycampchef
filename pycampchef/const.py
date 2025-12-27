from __future__ import annotations

from enum import IntEnum

from .models import VendorConfig

class WsId(IntEnum):
    MODE = 0x01
    DEVICE_INFO = 0x02
    TRANSITIONING = 0x03
    PELLET_LEVEL = 0x04
    LAST_FAULT = 0x05
    CHAMBER_TEMP = 0x06
    PROBE_MIN = 0x10
    PROBE_MAX = 0x1F
    CLIENT_SECRET = 0x08
    WEB_ID = 0x09
    MODEL_FW = 0x30
    ESP_FW = 0x31
    WIFI_SSID = 0x20
    WIFI_PASSWORD = 0x21
    WIFI_STATUS = 0x22
    WIFI_SCANNING = 0x23
    WIFI_SCAN_RESULTS = 0x24
    WIFI_RSSI = 0x25
    HTTP_ENDPOINT = 0x26
    WS_ENDPOINT = 0x27
    OTA_STATE = 0x34
    MULTIPLEX = 0xFF

class ModeName(IntEnum):
    STANDBY = 0x00
    FAN = 0x01
    FEED = 0x02
    RECORD = 0x03
    HIGH = 0x10
    RUN = 0x11
    COOK_PROGRAM = 0x12
    DEBUG = 0x7F


class WifiStatus(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3

class OtaState(IntEnum):
    IDLE = 0
    IN_PROGRESS = 1
    UNKNOWN = 255

VENDOR_CONFIGS = {
    "campchef": VendorConfig(
        name="CampChef",
        adv_name_prefix="CampChef:",
        service_uuid="0000efb0-0000-1000-8000-00805f9b34fb",
        uuid_base_prefix="7dbaefb0-6bc3-4b8c-9990-3509fb398a",
    ),
    "cabelas": VendorConfig(
        name="Cabelas",
        adv_name_prefix="Cabelas:",
        service_uuid="0000efb1-0000-1000-8000-00805f9b34fb",
        uuid_base_prefix="7dbaefb1-6bc3-4b8c-9990-3509fb398a",
    ),
    "kingsford": VendorConfig(
        name="Kingsford",
        adv_name_prefix="Kingsford:",
        service_uuid="0000efb2-0000-1000-8000-00805f9b34fb",
        uuid_base_prefix="7dbaefb2-6bc3-4b8c-9990-3509fb398a",
    ),
}
