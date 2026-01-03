#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
import re
import sys
from pathlib import Path
from collections import Counter
from typing import Dict, Iterator, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycampchef import GrillOta, GrillTelemetry
from pycampchef.const import OtaState, WsId
from pycampchef.decoder import decode_notify_payload

GRILL_MODE_NAMES = {
    0x00: "UNKNOWN",
    0x01: "STANDBY",
    0x02: "FAN",
    0x03: "RECORD",
    0x04: "FEED",
    0x05: "HIGH",
    0x06: "RUN",
    0x07: "COOK_PROGRAM",
    0x08: "DEBUG",
}

BLE_CONFIGS = {
    "efb0": {
        "vendor": "CampChef",
        "scan_prefix": "CampChef:",
        "service": "0000efb0-0000-1000-8000-00805f9b34fb",
        "uuid_prefix": "7dbaefb0-6bc3-4b8c-9990-3509fb398a",
        "multiplex": "7dbaefb0-6bc3-4b8c-9990-3509fb398aff",
    },
    "efb1": {
        "vendor": "Cabelas",
        "scan_prefix": "Cabelas:",
        "service": "0000efb1-0000-1000-8000-00805f9b34fb",
        "uuid_prefix": "7dbaefb1-6bc3-4b8c-9990-3509fb398a",
        "multiplex": "7dbaefb1-6bc3-4b8c-9990-3509fb398aff",
    },
    "efb2": {
        "vendor": "Kingsford",
        "scan_prefix": "Kingsford:",
        "service": "0000efb2-0000-1000-8000-00805f9b34fb",
        "uuid_prefix": "7dbaefb2-6bc3-4b8c-9990-3509fb398a",
        "multiplex": "7dbaefb2-6bc3-4b8c-9990-3509fb398aff",
    },
}


def _friendly_uuid_name(uuid: str) -> Optional[str]:
    u = uuid.lower()
    for cfg in BLE_CONFIGS.values():
        if u == cfg["service"]:
            return f"{cfg['vendor']} service"
        if u == cfg["multiplex"]:
            return f"{cfg['vendor']} multiplex"
        if u.startswith(cfg["uuid_prefix"]):
            suffix = u.replace("-", "")[-2:]
            try:
                ws_id = int(suffix, 16)
                return f"{cfg['vendor']} ws_id 0x{ws_id:02x}"
            except ValueError:
                return f"{cfg['vendor']} ws_id"
    return None


def _iter_att_packets_pyshark(
    path: str,
    *,
    tshark_path: Optional[str] = None,
    debug: bool = False,
    debug_limit: int = 25,
) -> Iterator[Tuple[int, Optional[int], int, Optional[int], bytes, dict]]:
    try:
        import pyshark
    except Exception as e:
        raise RuntimeError(f"pyshark is required: {e}") from e
    import asyncio

    def _hex_to_bytes(value: Optional[str]) -> bytes:
        if not value:
            return b""
        return bytes.fromhex(value.replace(":", ""))

    last_read_handle: Optional[int] = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    capture = pyshark.FileCapture(
        path,
        keep_packets=False,
        tshark_path=tshark_path,
        eventloop=loop,
        display_filter="btatt",
    )
    debug_left = max(0, debug_limit)
    debug_fields_shown: set[int] = set()
    try:
        for pkt in capture:
            if not hasattr(pkt, "btatt"):
                continue
            btatt = pkt.btatt
            opcode = btatt.get_field_value("opcode")
            if opcode is None:
                continue
            try:
                att_opcode = int(opcode, 16)
            except ValueError:
                continue
            acl_handle: Optional[int] = None
            if hasattr(pkt, "bthci_acl"):
                bthci_acl = pkt.bthci_acl
                handle_val = (
                    bthci_acl.get_field_value("handle")
                    or bthci_acl.get_field_value("connection_handle")
                )
                if handle_val is not None:
                    try:
                        acl_handle = int(handle_val, 16)
                    except ValueError:
                        acl_handle = None
            handle_val = btatt.get_field_value("handle")
            att_handle = None
            if handle_val is not None:
                try:
                    att_handle = int(handle_val, 16)
                except ValueError:
                    att_handle = None
            value_hex = btatt.get_field_value("value_raw") or btatt.get_field_value("value")
            value = _hex_to_bytes(value_hex)
            if debug and debug_left > 0:
                debug_left -= 1
                value_show = (value_hex or "").replace(":", "")
                if len(value_show) > 64:
                    value_show = value_show[:64] + "..."
                handle_show = f"0x{att_handle:04x}" if att_handle is not None else "-"
                acl_show = f"0x{acl_handle:04x}" if acl_handle is not None else "-"
                print(
                    f"debug btatt op=0x{att_opcode:02x} acl={acl_show} handle={handle_show} "
                    f"value={value_show}"
                )
                if att_opcode in (0x09, 0x11) and att_opcode not in debug_fields_shown:
                    debug_fields_shown.add(att_opcode)
                    try:
                        field_names = list(btatt.field_names)
                    except Exception:
                        field_names = []
                    print(f"debug btatt fields op=0x{att_opcode:02x}: {field_names}")
                    for name in field_names:
                        if "uuid" in name or "handle" in name or "value" in name or "attribute" in name:
                            try:
                                field_val = btatt.get_field_value(name)
                            except Exception:
                                field_val = None
                            if field_val is not None:
                                print(f"debug btatt field {name}={field_val}")

            if att_opcode == 0x0A and att_handle is not None:
                last_read_handle = att_handle
                yield 0, acl_handle, att_opcode, att_handle, b"", {}
                continue
            if att_opcode == 0x0B:
                yield 0, acl_handle, att_opcode, last_read_handle, value, {}
                continue
            fields = {}
            for key in ("uuid16", "uuid128", "service_uuid16", "service_uuid128"):
                val = btatt.get_field_value(key)
                if val is not None:
                    fields[key] = val
            if att_opcode in (0x09, 0x11):
                for key in ("attribute_data", "handle", "group_end_handle", "characteristic_properties"):
                    val = btatt.get_field_value(key)
                    if val is not None:
                        fields[key] = val
            yield 0, acl_handle, att_opcode, att_handle, value, fields
    finally:
        capture.close()
        loop.close()


def _telemetry_to_dict(telem: GrillTelemetry) -> dict:
    probe = telem.probe
    chamber = telem.chamber
    wifi = telem.wifi
    temp_f = None
    if probe and probe.temp_f is not None:
        temp_f = probe.temp_f
    elif chamber:
        temp_f = chamber.temp_f
    out = {
        "ws_id": telem.ws_id,
        "probe_index": probe.index if probe else None,
        "probe_i16": probe.i16 if probe else None,
        "chamber_i16": chamber.i16 if chamber else None,
        "wifi_rssi_dbm": wifi.rssi_dbm if wifi else None,
        "temp_f": temp_f,
    }
    out = {k: v for k, v in out.items() if v is not None}
    out["raw_hex"] = telem.raw.hex()
    return out


def _opcode_name(opcode: int) -> str:
    names = {
        0x08: "READ_BY_TYPE_REQ",
        0x09: "READ_BY_TYPE_RESP",
        0x10: "READ_BY_GROUP_REQ",
        0x11: "READ_BY_GROUP_RESP",
        0x0A: "READ_REQ",
        0x0B: "READ_RESP",
        0x12: "WRITE_REQ",
        0x13: "WRITE_RESP",
        0x1B: "NOTIFY",
        0x1D: "INDICATE",
        0x52: "WRITE_CMD",
    }
    return names.get(opcode, f"OP_0x{opcode:02x}")


def _parse_attribute_data_handle(attr: str) -> Optional[int]:
    match = re.search(r"Characteristic Handle:\\s*0x([0-9a-fA-F]+)", attr)
    if not match:
        return None
    try:
        return int(match.group(1), 16)
    except ValueError:
        return None


def _parse_attribute_data_uuid(attr: str) -> Optional[str]:
    match = re.search(r"UUID128:\\s*([0-9a-fA-F:]+)", attr)
    if match:
        uuid_hex = match.group(1).replace(":", "")
        if len(uuid_hex) == 32:
            return (
                f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                f"{uuid_hex[16:20]}-{uuid_hex[20:32]}"
            )
    match = re.search(r"UUID:\\s*0x([0-9a-fA-F]+)", attr)
    if match:
        try:
            uuid16 = int(match.group(1), 16)
        except ValueError:
            return None
        return f"0000{uuid16:04x}-0000-1000-8000-00805f9b34fb"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse PacketLogger .pklg for CampChef BLE notifications.")
    parser.add_argument("path", nargs="?", default="bluetoothd-hci-latest.pklg")
    parser.add_argument("--dump", action="store_true", help="Dump decoded notifications.")
    parser.add_argument("--trace-ws", type=lambda v: int(v, 0), help="Trace ws_id notifications.")
    parser.add_argument("--context", type=int, default=6, help="Packets of context for --trace-ws.")
    parser.add_argument("--resolve-handle", type=lambda v: int(v, 0), help="Resolve ATT handle to UUID.")
    parser.add_argument("--dump-gatt", action="store_true", help="Dump discovered services and characteristics.")
    parser.add_argument("--summary", action="store_true", help="Print summary counts.")
    parser.add_argument("--verbose", action="store_true", help="Show sensitive values like client_secret.")
    parser.add_argument("--tshark-path", help="Path to tshark for pyshark parsing.")
    parser.add_argument("--debug", action="store_true", help="Print the first btatt packets for troubleshooting.")
    parser.add_argument("--debug-limit", type=int, default=25, help="Max packets to print for --debug.")
    args = parser.parse_args()

    ws_counts = Counter()
    unknown_ws = Counter()
    cccd_writes = Counter()
    writes_0100: Dict[int, int] = {}
    total = 0
    decoded = 0
    recent_packets: Dict[int, list] = {}
    pending_read_by_type: Dict[int, Optional[int]] = {}
    pending_read_handle: Dict[int, int] = {}
    handle_uuid: Dict[int, str] = {}
    handle_props: Dict[int, int] = {}
    service_ranges: list[tuple[int, int, str]] = []
    notify_handles: set[int] = set()
    notify_counts: Dict[int, int] = {}
    campchef_cfg = BLE_CONFIGS["efb0"]
    campchef_service = campchef_cfg["service"]
    campchef_prefix = campchef_cfg["uuid_prefix"]
    campchef_acl_handles: set[int] = set()

    def _is_campchef_handle(handle: Optional[int]) -> bool:
        if handle is None:
            return False
        uuid = handle_uuid.get(handle)
        if uuid and uuid.lower().startswith(campchef_prefix):
            return True
        for start_handle, end_handle, uuid in service_ranges:
            if start_handle <= handle <= end_handle:
                return uuid.lower() == campchef_service
        return False

    def _print_telem(telem: GrillTelemetry, prefix: str) -> None:
        handled = False
        wifi = telem.wifi
        mode = telem.mode
        status = telem.status
        device = telem.device
        chamber = telem.chamber
        probe = telem.probe
        ota: Optional[GrillOta] = telem.ota

        if wifi and wifi.rssi_dbm is not None:
            print(f"{prefix} wifi_rssi_dbm={wifi.rssi_dbm}")
            handled = True

        if mode is not None:
            payload_hex = telem.raw[1:].hex() if len(telem.raw) > 1 else ""
            mode_code = telem.raw[1] if len(telem.raw) > 1 else None
            mode_name = mode.mode.name if mode.mode else "UNKNOWN"
            print(
                f"{prefix} mode={mode_name} "
                f"mode_code_raw={mode_code} "
                f"mode_raw_hex={payload_hex}"
            )
            sub_prefix = "  " if prefix == "notify" else f"{prefix} "
            if mode.set_temp_f is not None:
                print(f"{sub_prefix}set_temp_f={mode.set_temp_f}")
            if mode.smoke_level is not None:
                print(f"{sub_prefix}smoke_level={mode.smoke_level}")
            if mode.fan_level is not None:
                print(f"{sub_prefix}fan_level={mode.fan_level}")
            handled = True

        if status and status.transitioning is not None:
            print(f"{prefix} transitioning={status.transitioning}")
            handled = True

        if status and status.pellet_level is not None:
            print(f"{prefix} pellet_level={status.pellet_level}")
            handled = True

        if status and status.has_fault is not None:
            payload_hex = telem.raw[1:].hex() if len(telem.raw) > 1 else ""
            print(f"{prefix} has_fault={status.has_fault} fault_raw={payload_hex}")
            handled = True

        if ota and ota.state is not None:
            ota_raw = telem.raw[1] if len(telem.raw) > 1 else None
            if ota.state == OtaState.IN_PROGRESS:
                print(
                    f"{prefix} ota_state={ota.state.name} "
                    f"progress={ota.progress_percent} "
                    f"ota_raw={ota_raw}"
                )
            else:
                print(f"{prefix} ota_state={ota.state.name} ota_raw={ota_raw}")
            handled = True

        if device and device.info is not None:
            info = device.info
            caps = device.capabilities
            print(
                f"{prefix} device_info="
                f"model_id={info.model_id} "
                f"capability_flags={info.capability_flags} "
                f"max_grill_temp_f={info.max_grill_temp_f}"
            )
            if caps is not None:
                print(f"{prefix} capabilities:")
                print(f"  known={caps.capabilities_known}")
                print(f"  probe_count={caps.probe_count}")
                print(f"  sku={caps.sku}")
                print(f"  min_temp_f={caps.min_temp_f}")
                print(f"  spec_max_temp_f={caps.spec_max_temp_f}")
                print(f"  smoke_threshold_f={caps.smoke_threshold_f}")
                print(f"  high_temp_threshold_f={caps.high_temp_threshold_f}")
                print(f"  low_smoke_write_command={caps.low_smoke_write_command}")
                print(f"  high_smoke_write_command={caps.high_smoke_write_command}")
                print(f"  has_high_temp_setting={caps.has_high_temp_setting}")
                print(f"  has_night_mode={caps.has_night_mode}")
                print(f"  max_temp_f={caps.max_temp_f}")
            handled = True

        if device and device.client_secret is not None:
            if args.verbose:
                print(f"{prefix} client_secret={device.client_secret}")
            else:
                print(f"{prefix} client_secret=***")
            handled = True

        if device and device.web_id is not None:
            print(f"{prefix} web_id={device.web_id}")
            handled = True

        if device and device.http_endpoint is not None:
            print(f"{prefix} http_endpoint={device.http_endpoint}")
            handled = True

        if device and device.ws_endpoint is not None:
            print(f"{prefix} ws_endpoint={device.ws_endpoint}")
            handled = True

        if wifi and wifi.ssid is not None:
            print(f"{prefix} wifi_ssid={wifi.ssid}")
            handled = True
        elif wifi and wifi.ssid is None and telem.ws_id == WsId.WIFI_SSID:
            print(f"{prefix} wifi_ssid=<none>")
            handled = True

        if wifi and wifi.status is not None:
            print(f"{prefix} wifi_status={wifi.status.name}")
            handled = True

        if wifi and wifi.scanning is not None:
            print(f"{prefix} wifi_scanning={wifi.scanning}")
            handled = True

        if device and device.model_fw is not None:
            print(f"{prefix} model_fw={device.model_fw}")
            handled = True

        if device and device.esp_fw is not None:
            print(f"{prefix} esp_fw={device.esp_fw}")
            handled = True

        if chamber is not None:
            print(f"{prefix} chamber_f={chamber.temp_f:.1f}")
            handled = True

        if probe is not None:
            idx = probe.index + 1
            if probe.connected:
                if probe.temp_f is not None:
                    print(f"{prefix} probe{idx}_f={probe.temp_f:.1f}")
                else:
                    print(f"{prefix} probe{idx} (undecoded)")
            else:
                print(f"{prefix} probe{idx} (disconnected)")
            handled = True

        if not handled:
            ws_id = getattr(telem, "ws_id", None)
            if ws_id is not None:
                raw = getattr(telem, "raw", b"")
                if raw:
                    print(f"{prefix} ws=0x{ws_id:02x} payload={raw.hex()}")
                else:
                    print(f"{prefix} ws=0x{ws_id:02x}")
            else:
                print(f"{prefix}")

    def _handle_telem(telem: GrillTelemetry, ts: int, source: str) -> None:
        nonlocal decoded
        if telem.ws_id is not None:
            ws_counts[telem.ws_id] += 1
        is_known = any(
            [
                telem.probe is not None,
                telem.chamber is not None,
                telem.wifi is not None,
                telem.status is not None,
                telem.device is not None,
                telem.ota is not None,
                telem.mode is not None,
            ]
        )
        if telem.ws_id is not None and not is_known:
            unknown_ws[telem.ws_id] += 1
        if telem.ws_id is not None:
            decoded += 1
        if args.dump:
            d = _telemetry_to_dict(telem)
            d["ts"] = ts
            print(d)
        elif not args.summary:
            prefix = "notify" if source == "notify" else f"read ws=0x{telem.ws_id:02x}"
            _print_telem(telem, prefix)

    att_iter = _iter_att_packets_pyshark(
        args.path,
        tshark_path=args.tshark_path,
        debug=args.debug,
        debug_limit=args.debug_limit,
    )

    for ts, acl_handle, att_opcode, att_handle, value, fields in att_iter:
        acl_key = acl_handle if acl_handle is not None else 0
        if att_handle is not None:
            uuid16 = fields.get("uuid16") or fields.get("service_uuid16")
            uuid128 = fields.get("uuid128") or fields.get("service_uuid128")
            if uuid128:
                uuid_hex = uuid128.replace(":", "")
                if len(uuid_hex) == 32:
                    handle_uuid.setdefault(
                        att_handle,
                        f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                        f"{uuid_hex[16:20]}-{uuid_hex[20:32]}",
                    )
            elif uuid16:
                try:
                    uuid16_int = int(uuid16, 16)
                except ValueError:
                    uuid16_int = None
                if uuid16_int is not None and uuid16_int != 0x2803:
                    handle_uuid.setdefault(
                        att_handle,
                        f"0000{uuid16_int:04x}-0000-1000-8000-00805f9b34fb",
                    )
        if att_opcode == 0x08 and len(value) >= 4:
            # Read By Type Request: end_handle(2), type(2|16)
            att_type = None
            type_bytes = value[2:]
            if len(type_bytes) == 2:
                att_type = struct.unpack_from("<H", type_bytes, 0)[0]
            pending_read_by_type[acl_key] = att_type
        elif att_opcode == 0x09:
            if len(value) < 1 and fields.get("attribute_data"):
                try:
                    value = bytes.fromhex(fields["attribute_data"].replace(":", ""))
                except ValueError:
                    value = b""
            if len(value) >= 1:
                # Read By Type Response: [length][handle+value]*
                req_type = pending_read_by_type.get(acl_key)
                entry_len = value[0]
                if req_type == 0x2803 or entry_len in (7, 21):
                    entries = value[1:]
                    for i in range(0, len(entries), entry_len):
                        chunk = entries[i : i + entry_len]
                        if len(chunk) < entry_len:
                            break
                        if entry_len == 7:
                            _decl_handle, props, val_handle, uuid16 = struct.unpack_from(
                                "<HBHH", chunk, 0
                            )
                            handle_uuid[val_handle] = (
                                f"0000{uuid16:04x}-0000-1000-8000-00805f9b34fb"
                            )
                            handle_props[val_handle] = props
                        elif entry_len == 21:
                            val_handle = struct.unpack_from("<H", chunk, 3)[0]
                            handle_props[val_handle] = chunk[2]
                            uuid128 = chunk[5:21]
                            uuid_hex = uuid128[::-1].hex()
                            handle_uuid[val_handle] = (
                                f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                                f"{uuid_hex[16:20]}-{uuid_hex[20:32]}"
                            )
            elif fields:
                handle_val = fields.get("handle")
                uuid16 = fields.get("uuid16")
                uuid128 = fields.get("uuid128")
                props = fields.get("characteristic_properties")
                attr = fields.get("attribute_data")
                val_handle = None
                if attr:
                    val_handle = _parse_attribute_data_handle(attr)
                if val_handle is None and handle_val is not None:
                    try:
                        val_handle = int(handle_val, 16)
                    except ValueError:
                        val_handle = None
                if val_handle is not None:
                    if uuid16 is not None:
                        try:
                            uuid16_int = int(uuid16, 16)
                        except ValueError:
                            uuid16_int = None
                        if uuid16_int is not None and uuid16_int != 0x2803:
                            handle_uuid[val_handle] = (
                                f"0000{uuid16_int:04x}-0000-1000-8000-00805f9b34fb"
                            )
                    elif uuid128 is not None:
                        uuid_hex = uuid128.replace(":", "")
                        if len(uuid_hex) == 32:
                            handle_uuid[val_handle] = (
                                f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                                f"{uuid_hex[16:20]}-{uuid_hex[20:32]}"
                            )
                    elif attr:
                        uuid_from_attr = _parse_attribute_data_uuid(attr)
                        if uuid_from_attr:
                            handle_uuid[val_handle] = uuid_from_attr
                    if props is not None:
                        try:
                            handle_props[val_handle] = int(props, 16)
                        except ValueError:
                            pass
        elif att_opcode == 0x11:
            if len(value) < 1 and fields.get("attribute_data"):
                try:
                    value = bytes.fromhex(fields["attribute_data"].replace(":", ""))
                except ValueError:
                    value = b""
            if len(value) >= 1:
                # Read By Group Type Response (Primary Service): [length][start][end][uuid]*
                entry_len = value[0]
                entries = value[1:]
                if entry_len in (6, 20):
                    for i in range(0, len(entries), entry_len):
                        chunk = entries[i : i + entry_len]
                        if len(chunk) < entry_len:
                            break
                        start_handle, end_handle = struct.unpack_from("<HH", chunk, 0)
                        if entry_len == 6:
                            uuid16 = struct.unpack_from("<H", chunk, 4)[0]
                            uuid = f"0000{uuid16:04x}-0000-1000-8000-00805f9b34fb"
                        else:
                            uuid128 = chunk[4:20]
                            uuid_hex = uuid128[::-1].hex()
                            uuid = (
                                f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                                f"{uuid_hex[16:20]}-{uuid_hex[20:32]}"
                            )
                        service_ranges.append((start_handle, end_handle, uuid))
                        if uuid.lower() == campchef_service and acl_handle is not None:
                            campchef_acl_handles.add(acl_handle)
            elif fields:
                handle_val = fields.get("handle")
                end_val = fields.get("group_end_handle")
                uuid16 = fields.get("uuid16") or fields.get("service_uuid16")
                uuid128 = fields.get("uuid128") or fields.get("service_uuid128")
                try:
                    start_handle = int(handle_val, 16) if handle_val is not None else None
                    end_handle = int(end_val, 16) if end_val is not None else None
                except ValueError:
                    start_handle = None
                    end_handle = None
                uuid = None
                if uuid16 is not None:
                    try:
                        uuid16_int = int(uuid16, 16)
                    except ValueError:
                        uuid16_int = None
                    if uuid16_int is not None:
                        uuid = f"0000{uuid16_int:04x}-0000-1000-8000-00805f9b34fb"
                elif uuid128 is not None:
                    uuid_hex = uuid128.replace(":", "")
                    if len(uuid_hex) == 32:
                        uuid = (
                            f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                            f"{uuid_hex[16:20]}-{uuid_hex[20:32]}"
                        )
                if start_handle is not None and end_handle is not None and uuid is not None:
                    service_ranges.append((start_handle, end_handle, uuid))
                    if uuid.lower() == campchef_service and acl_handle is not None:
                        campchef_acl_handles.add(acl_handle)

        if att_opcode == 0x0A and att_handle is not None:
            pending_read_handle[acl_key] = att_handle
        elif att_opcode == 0x0B and value:
            read_handle = pending_read_handle.get(acl_key)
            if read_handle is not None:
                uuid = handle_uuid.get(read_handle)
                if uuid:
                    uuid_lower = uuid.lower()
                    if uuid_lower.startswith(campchef_prefix):
                        ws_hex = uuid_lower.replace("-", "")[-2:]
                        try:
                            ws_id = int(ws_hex, 16)
                            telem = decode_notify_payload(bytes([ws_id]) + value)
                            _handle_telem(telem, ts, "read")
                        except ValueError:
                            pass

        if att_opcode in (0x12, 0x52) and att_handle is not None and len(value) >= 2:
            if value[:2] == b"\x01\x00":
                if _is_campchef_handle(att_handle):
                    cccd_writes[att_handle] += 1
                    writes_0100[att_handle] = writes_0100.get(att_handle, 0) + 1

        if att_opcode in (0x12, 0x52, 0x0A, 0x0B, 0x13):
            recent_packets.setdefault(acl_key, []).append(
                (ts, att_opcode, att_handle, value[:16])
            )
            if len(recent_packets[acl_key]) > args.context:
                recent_packets[acl_key].pop(0)

        if att_opcode not in (0x1B, 0x1D):
            continue
        if campchef_acl_handles and acl_handle is not None and acl_handle not in campchef_acl_handles:
            continue
        if not _is_campchef_handle(att_handle):
            continue
        total += 1
        if att_handle is not None:
            notify_handles.add(att_handle)
            notify_counts[att_handle] = notify_counts.get(att_handle, 0) + 1
        service_uuid = None
        if att_handle is not None:
            for start_handle, end_handle, uuid in service_ranges:
                if start_handle <= att_handle <= end_handle:
                    service_uuid = uuid
                    break
        value_uuid = handle_uuid.get(att_handle) if att_handle is not None else None
        if value_uuid == "00002a05-0000-1000-8000-00805f9b34fb":
            if args.dump and len(value) >= 4:
                start, end = struct.unpack_from("<HH", value, 0)
                print(
                    {
                        "service_changed": True,
                        "start_handle": start,
                        "end_handle": end,
                        "ts": ts,
                    }
                )
            continue
        if service_uuid == "00001801-0000-1000-8000-00805f9b34fb":
            continue

        telem = decode_notify_payload(value)
        _handle_telem(telem, ts, "notify")
        if args.trace_ws is not None and telem.ws_id == args.trace_ws:
            acl_label = f"0x{acl_handle:04x}" if acl_handle is not None else "-"
            print(
                f"TRACE ws_id=0x{telem.ws_id:02x} ts={ts} acl={acl_label} "
                f"att_handle=0x{(att_handle or 0):04x} payload={telem.raw.hex()}"
            )
            if value_uuid:
                print(f"  handle_uuid={value_uuid}")
            if service_uuid:
                print(f"  service_uuid={service_uuid}")
            for r_ts, r_op, r_handle, r_value in recent_packets.get(acl_key, []):
                handle_str = f"0x{r_handle:04x}" if r_handle is not None else "-"
                print(
                    f"  {r_ts} {_opcode_name(r_op)} handle={handle_str} "
                    f"value={r_value.hex()}"
                )

    if args.summary:
        print(f"records: {total}")
        print(f"decoded: {decoded}")
        if ws_counts:
            print("ws_id counts:")
            for ws_id, count in sorted(ws_counts.items()):
                print(f"  0x{ws_id:02x}: {count}")
        if unknown_ws:
            print("unknown ws_id counts:")
            for ws_id, count in sorted(unknown_ws.items()):
                print(f"  0x{ws_id:02x}: {count}")
        if cccd_writes:
            print("writes of 0x0100 by handle:")
            for h, count in sorted(cccd_writes.items()):
                print(f"  0x{h:04x}: {count}")
            print("0x0100 write -> uuid mapping:")
            for h, count in sorted(writes_0100.items()):
                candidates = [h, h - 1, h - 2]
                mapped = []
                for vh in candidates:
                    uuid = handle_uuid.get(vh)
                    if uuid:
                        name = _friendly_uuid_name(uuid)
                        label = f" {name}" if name else ""
                        props = handle_props.get(vh)
                        props_label = f" props=0x{props:02x}" if props is not None else ""
                        notify_label = " notify_on_handle" if notify_counts.get(vh) else ""
                        mapped.append(
                            f"0x{vh:04x} {uuid}{label}{props_label}{notify_label}"
                        )
                if mapped:
                    print(f"  0x{h:04x} x{count} -> " + " | ".join(mapped))
        campchef_handles = [
            h for h, uuid in handle_uuid.items() if uuid.lower().startswith(campchef_prefix)
        ]
        if campchef_handles:
            print("campchef notifications by uuid:")
            for h in sorted(campchef_handles):
                count = notify_counts.get(h, 0)
                if count == 0:
                    continue
                uuid = handle_uuid[h]
                name = _friendly_uuid_name(uuid)
                label = f" {name}" if name else ""
                print(f"  0x{h:04x} {uuid}{label} {count}")
    if args.resolve_handle is not None:
        uuid = handle_uuid.get(args.resolve_handle)
        if uuid:
            name = _friendly_uuid_name(uuid)
            label = f" ({name})" if name else ""
            print(f"handle 0x{args.resolve_handle:04x} -> {uuid}{label}")
        else:
            print(f"handle 0x{args.resolve_handle:04x} -> <not found>")
    if args.dump_gatt:
        campchef = sorted(
            (h, uuid)
            for h, uuid in handle_uuid.items()
            if uuid.lower().startswith(campchef_prefix)
        )
        print("campchef characteristics:")
        for h, uuid in campchef:
            name = _friendly_uuid_name(uuid)
            label = f" {name}" if name else ""
            print(f"  0x{h:04x} {uuid}{label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
