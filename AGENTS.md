# AGENTS.md

Project: pycampchef 

Key Structure
- Python package: `pycampchef/`
- Tools: `tools/pycampchef_cli.py`, `tools/pycampchef_parse_pklg.py`
- Public API: package root `pycampchef/__init__.py`

Module Layout
- `pycampchef/client.py`: BLE session (connect/read/write/notify), exposes `commands` property
- `pycampchef/commands.py`: high-level actions (mode, Wi‑Fi, firmware read)
- `pycampchef/decoder.py`: decode multiplexed wsId payloads into telemetry
- `pycampchef/protocol.py`: payload encoders (mode write)
- `pycampchef/discovery.py`: vendor inference + `async_discover`
- `pycampchef/const.py`: enums/IDs (WsId, ModeName, WifiStatus, OtaState), vendor configs
- `pycampchef/models.py`: dataclasses (GrillTelemetry + domain models)

Telemetry Notes
- `GrillTelemetry` is the envelope: `ws_id`, `raw`, optional domain objects.
- Domain models: `GrillMode`, `GrillWifi`, `GrillStatus`, `GrillProbe`, `GrillChamber`, `GrillDevice`, `GrillOta`.
- `ws_id` is `WsId` for known values, otherwise raw `int`.

Tools
- Tools use a `sys.path` bootstrap to import the package from repo root.
- CLI entrypoint name: `pycampchef-cli` (tool script `tools/pycampchef_cli.py`).

Conventions
- Prefer importing from `pycampchef` package root for public API.
- Keep raw bytes only on `GrillTelemetry.raw`; avoid per-domain raw fields.
