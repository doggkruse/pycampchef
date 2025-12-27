from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from pycampchef import CampChefBleClient, async_discover
from pycampchef.const import OtaState, VENDOR_CONFIGS, WsId
from pycampchef.decoder import decode_notify_payload

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("pycampchef")


async def main() -> None:
    p = argparse.ArgumentParser(prog="pycampchef-cli")
    p.add_argument(
        "--address",
        help=(
            "Device identifier. On macOS this may be a CoreBluetooth UUID; "
            "prefer omitting and letting scan select a BLEDevice."
        ),
    )
    p.add_argument("--scan", action="store_true", help="Scan and print CampChef devices, then exit.")
    p.add_argument("--verbose", action="store_true")

    p.add_argument(
        "--stream",
        action="store_true",
        help="Stream notifications until Ctrl+C.",
    )

    sub = p.add_subparsers(dest="cmd", required=False)
    sp = sub.add_parser("set-temp")
    sp.add_argument("temp", type=int)

    sp = sub.add_parser("set-smoke")
    sp.add_argument("smoke", type=int)

    sp = sub.add_parser("set-fan")
    sp.add_argument("fan", type=int)

    sp = sub.add_parser("wifi-scan")
    sp.add_argument("enabled", type=int, choices=[0, 1])
    sp.add_argument("--timeout", type=float, default=60.0)

    sp = sub.add_parser("wifi-credentials")
    sp.add_argument("ssid")
    sp.add_argument("password")
    sp.add_argument("--timeout", type=float, default=60.0)

    args = p.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.scan:
        devs = await async_discover()
        for dev, name, vendor in devs:
            print(f"{dev.address}  {name}  vendor={vendor.name}")
        return

    address: Optional[str] = args.address
    device = None
    vendor = None
    if not address:
        devs = await async_discover()
        if not devs:
            raise SystemExit("No supported devices found. Use --scan or provide --address.")
        device = devs[0][0]
        vendor = devs[0][2]
        _LOGGER.info(
            "Using first discovered device: %s (%s) vendor=%s",
            devs[0][1],
            device.address,
            vendor.name,
        )
    else:
        # Try to infer vendor from a scan result matching the address.
        devs = await async_discover()
        for dev, _name, v in devs:
            if dev.address == address:
                vendor = v
                break

    async def on_telem(telem):
        handled = False
        wifi = telem.wifi
        mode = telem.mode
        status = telem.status
        device = telem.device
        chamber = telem.chamber
        probe = telem.probe
        ota = telem.ota

        if wifi and wifi.rssi_dbm is not None:
            print(f"notify wifi_rssi_dbm={wifi.rssi_dbm}")
            handled = True

        if mode is not None:
            payload_hex = telem.raw[1:].hex() if len(telem.raw) > 1 else ""
            mode_code = telem.raw[1] if len(telem.raw) > 1 else None
            mode_name = mode.mode.name if mode.mode else "UNKNOWN"
            print(
                f"notify mode={mode_name} "
                f"mode_code_raw={mode_code} "
                f"mode_raw_hex={payload_hex}"
            )
            if mode.set_temp_f is not None:
                print(f"  set_temp_f={mode.set_temp_f}")
            if mode.smoke_level is not None:
                print(f"  smoke_level={mode.smoke_level}")
            if mode.fan_level is not None:
                print(f"  fan_level={mode.fan_level}")
            handled = True

        if status and status.transitioning is not None:
            print(f"notify transitioning={status.transitioning}")
            handled = True

        if status and status.pellet_level is not None:
            print(f"notify pellet_level={status.pellet_level}")
            handled = True

        if status and status.has_fault is not None:
            payload_hex = telem.raw[1:].hex() if len(telem.raw) > 1 else ""
            print(f"notify has_fault={status.has_fault} fault_raw={payload_hex}")
            handled = True

        if ota and ota.state is not None:
            ota_raw = telem.raw[1] if len(telem.raw) > 1 else None
            if ota.state == OtaState.IN_PROGRESS:
                print(
                    f"notify ota_state={ota.state.name} "
                    f"progress={ota.progress_percent} "
                    f"ota_raw={ota_raw}"
                )
            else:
                print(f"notify ota_state={ota.state.name} ota_raw={ota_raw}")
            handled = True

        if device and device.info is not None:
            info = device.info
            caps = device.capabilities
            print(
                "notify device_info="
                f"model_id={info.model_id} "
                f"capability_flags={info.capability_flags} "
                f"max_grill_temp_f={info.max_grill_temp_f}"
            )
            if caps is not None:
                print("notify capabilities:")
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
                print(f"notify client_secret={device.client_secret}")
            else:
                print("notify client_secret=***")
            handled = True

        if device and device.web_id is not None:
            print(f"notify web_id={device.web_id}")
            handled = True

        if device and device.http_endpoint is not None:
            print(f"notify http_endpoint={device.http_endpoint}")
            handled = True

        if device and device.ws_endpoint is not None:
            print(f"notify ws_endpoint={device.ws_endpoint}")
            handled = True

        if wifi and wifi.ssid is not None:
            print(f"notify wifi_ssid={wifi.ssid}")
            handled = True
        elif wifi and wifi.ssid is None and telem.ws_id == WsId.WIFI_SSID:
            print("notify wifi_ssid=<none>")
            handled = True

        if wifi and wifi.status is not None:
            print(f"notify wifi_status={wifi.status.name}")
            handled = True

        if wifi and wifi.scanning is not None:
            print(f"notify wifi_scanning={wifi.scanning}")
            handled = True

        if device and device.model_fw is not None:
            print(f"notify model_fw={device.model_fw}")
            handled = True

        if device and device.esp_fw is not None:
            print(f"notify esp_fw={device.esp_fw}")
            handled = True

        if chamber is not None:
            print(f"notify chamber_f={chamber.temp_f:.1f}")
            handled = True

        if probe is not None:
            idx = probe.index + 1
            if probe.connected:
                if probe.temp_f is not None:
                    print(f"notify probe{idx}_f={probe.temp_f:.1f}")
                else:
                    print(f"notify probe{idx} (undecoded)")
            else:
                print(f"notify probe{idx} (disconnected)")
            handled = True

        if not handled:
            ws_id = getattr(telem, "ws_id", None)
            if ws_id is not None:
                raw = getattr(telem, "raw", b"")
                if raw:
                    print(f"notify ws=0x{ws_id:02x} payload={raw.hex()}")
                else:
                    print(f"notify ws=0x{ws_id:02x}")
            else:
                print("notify")

    target = address if address else device
    c = CampChefBleClient(
        target,
        vendor=vendor or VENDOR_CONFIGS["campchef"],
        on_telemetry=on_telem,
    )

    await c.connect()
    if args.verbose:
        chars = c.list_characteristics()
        if chars:
            print("characteristics:")
            for uuid, props in chars:
                props_str = ",".join(props)
                print(f"  {uuid} props={props_str}")
    # One-shot reads for all non-probe per-ws characteristics.
    caps = None
    for ws_id in range(0x00, 0x35):
        if 0x10 <= ws_id <= 0x1F:
            continue
        try:
            raw = await c.read_ws(ws_id)
        except Exception as exc:
            if args.verbose:
                print(f"read ws=0x{ws_id:02x} error={exc}")
            continue
        if not raw:
            if args.verbose:
                print(f"read ws=0x{ws_id:02x} empty")
            continue
        telem = decode_notify_payload(bytes([ws_id]) + raw)
        mode = telem.mode
        status = telem.status
        device = telem.device
        wifi = telem.wifi
        ota = telem.ota
        chamber = telem.chamber
        probe = telem.probe
        if mode is not None:
            payload_hex = telem.raw[1:].hex() if len(telem.raw) > 1 else ""
            mode_code = telem.raw[1] if len(telem.raw) > 1 else None
            mode_name = mode.mode.name if mode.mode else "UNKNOWN"
            print(
                f"read ws=0x{ws_id:02x} mode={mode_name} "
                f"mode_code_raw={mode_code} "
                f"mode_raw_hex={payload_hex}"
            )
            if mode.set_temp_f is not None:
                print(f"read ws=0x{ws_id:02x} set_temp_f={mode.set_temp_f}")
            if mode.smoke_level is not None:
                print(f"read ws=0x{ws_id:02x} smoke_level={mode.smoke_level}")
            if mode.fan_level is not None:
                print(f"read ws=0x{ws_id:02x} fan_level={mode.fan_level}")
        elif status and status.transitioning is not None:
            print(f"read ws=0x{ws_id:02x} transitioning={status.transitioning}")
        elif status and status.pellet_level is not None:
            print(f"read ws=0x{ws_id:02x} pellet_level={status.pellet_level}")
        elif status and status.has_fault is not None:
            payload_hex = telem.raw[1:].hex() if len(telem.raw) > 1 else ""
            print(f"read ws=0x{ws_id:02x} has_fault={status.has_fault} fault_raw={payload_hex}")
        elif ota and ota.state is not None:
            ota_raw = telem.raw[1] if len(telem.raw) > 1 else None
            if ota.state == OtaState.IN_PROGRESS:
                print(
                    f"read ws=0x{ws_id:02x} ota_state={ota.state.name} "
                    f"progress={ota.progress_percent} "
                    f"ota_raw={ota_raw}"
                )
            else:
                print(
                    f"read ws=0x{ws_id:02x} ota_state={ota.state.name} "
                    f"ota_raw={ota_raw}"
                )
        elif device and device.info is not None:
            info = device.info
            caps = device.capabilities
            print(
                f"read ws=0x{ws_id:02x} device_info="
                f"model_id={info.model_id} "
                f"capability_flags={info.capability_flags} "
                f"max_grill_temp_f={info.max_grill_temp_f}"
            )
            if caps is not None:
                print(f"read ws=0x{ws_id:02x} capabilities:")
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
        elif device and device.client_secret is not None:
            if args.verbose:
                print(f"read ws=0x{ws_id:02x} client_secret={device.client_secret}")
            else:
                print(f"read ws=0x{ws_id:02x} client_secret=***")
        elif device and device.web_id is not None:
            print(f"read ws=0x{ws_id:02x} web_id={device.web_id}")
        elif device and device.http_endpoint is not None:
            print(f"read ws=0x{ws_id:02x} http_endpoint={device.http_endpoint}")
        elif device and device.ws_endpoint is not None:
            print(f"read ws=0x{ws_id:02x} ws_endpoint={device.ws_endpoint}")
        elif wifi and wifi.ssid is not None:
            print(f"read ws=0x{ws_id:02x} wifi_ssid={wifi.ssid}")
        elif wifi and wifi.ssid is None and ws_id == WsId.WIFI_SSID:
            print(f"read ws=0x{ws_id:02x} wifi_ssid=<none>")
        elif wifi and wifi.status is not None:
            print(f"read ws=0x{ws_id:02x} wifi_status={wifi.status.name}")
        elif wifi and wifi.scanning is not None:
            print(f"read ws=0x{ws_id:02x} wifi_scanning={wifi.scanning}")
        elif device and device.model_fw is not None:
            print(f"read ws=0x{ws_id:02x} model_fw={device.model_fw}")
        elif device and device.esp_fw is not None:
            print(f"read ws=0x{ws_id:02x} esp_fw={device.esp_fw}")
        elif wifi and wifi.rssi_dbm is not None:
            print(f"read ws=0x{ws_id:02x} wifi_rssi_dbm={wifi.rssi_dbm}")
        elif chamber is not None:
            print(f"read ws=0x{ws_id:02x} chamber_f={chamber.temp_f:.1f}")
        elif probe is not None:
            idx = probe.index + 1
            if probe.connected:
                if probe.temp_f is not None:
                    print(f"read ws=0x{ws_id:02x} probe{idx}_f={probe.temp_f:.1f}")
                else:
                    print(f"read ws=0x{ws_id:02x} probe{idx} (undecoded)")
            else:
                print(f"read ws=0x{ws_id:02x} probe{idx} (disconnected)")
        else:
            print(f"read ws=0x{ws_id:02x} payload={raw.hex()}")

    # One-shot reads for probe slots based on model capabilities.
    probe_count = 4
    if "caps" in locals() and caps is not None:
        if caps.probe_count is not None:
            probe_count = caps.probe_count
    max_probes = min(probe_count, 16)
    for i in range(max_probes):
        ws_id = 0x10 + i
        try:
            raw = await c.read_ws(ws_id)
        except Exception:
            continue
        if len(raw) < 2:
            continue
        telem = decode_notify_payload(bytes([ws_id]) + raw)
        idx = i + 1
        probe = telem.probe
        if probe is None:
            print(f"read ws=0x{ws_id:02x} probe{idx} (missing)")
        elif probe.connected:
            if probe.temp_f is not None:
                print(f"read ws=0x{ws_id:02x} probe{idx}_f={probe.temp_f:.1f}")
            else:
                print(f"read ws=0x{ws_id:02x} probe{idx} (undecoded)")
        else:
            print(f"read ws=0x{ws_id:02x} probe{idx} (disconnected)")
    fw = await c.commands.read_firmware_string()
    if fw:
        print(f"firmware/model: {fw}")

    await c.start_notifications()

    async def read_mode_blob():
        return await c.commands.read_mode()

    if args.cmd:
        try:
            if args.cmd == "set-temp":
                mode = await read_mode_blob()
                if mode.smoke_level is None:
                    raise RuntimeError("Smoke level missing; cannot preserve value")
                await c.commands.set_temp_smoke(args.temp, mode.smoke_level)
            elif args.cmd == "set-smoke":
                mode = await read_mode_blob()
                if mode.set_temp_f is None:
                    raise RuntimeError("Set temp missing; cannot preserve value")
                await c.commands.set_temp_smoke(mode.set_temp_f, args.smoke)
            elif args.cmd == "set-fan":
                await c.commands.set_fan(args.fan)
            elif args.cmd == "wifi-scan":
                await c.commands.wifi_scan(bool(args.enabled))
                if args.enabled:
                    await c.commands.wait_wifi_scan_complete(timeout=args.timeout)
            elif args.cmd == "wifi-credentials":
                telem = await c.commands.wifi_credentials(
                    args.ssid, args.password, status_timeout=args.timeout
                )
                wifi = telem.wifi
                if wifi and wifi.status is not None:
                    print(f"wifi_status={wifi.status.name}")
            else:
                raise SystemExit(f"Unknown command {args.cmd}")
            print(f"command sent: {args.cmd}")
        except Exception as e:
            _LOGGER.error("Command failed: %s", e)
            await c.disconnect()
            return

    if args.stream or not args.cmd:
        print("streaming notifications; Ctrl+C to exit")
        try:
            while True:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            pass
    await c.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
