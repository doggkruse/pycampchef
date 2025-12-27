# pycampchef

Python library for Camp Chef / Cabelas / Kingsford grills, interacting via Bluetooth Low Energy.

This project is not affiliated with, endorsed by, or sponsored by Camp Chef, Cabelas, Kingsford, or any related brands.

## Install

```bash
python -m pip install pycampchef
```

## Quick Start

```python
import asyncio

from pycampchef import CampChefBleClient, async_discover


async def main():
    devices = await async_discover()
    if not devices:
        raise SystemExit("No supported devices found.")
    device, _name, vendor = devices[0]

    client = CampChefBleClient(device, vendor=vendor)
    await client.connect()
    await client.start_notifications()

    # Example: read and print setpoint temp.
    mode = await client.commands.read_mode()
    if mode.set_temp_f is not None:
        print(f"set_temp_f={mode.set_temp_f}")
    else:
        print("set_temp_f=<unknown>")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

## Tools (Repo Only)

Developer tools live in `tools/` and are not packaged:
- `tools/pycampchef_cli.py` for interactive BLE control
- `tools/pycampchef_parse_pklg.py` for PacketLogger parsing

## Platform Support

BLE is provided by `bleak` and depends on the host OS Bluetooth stack:
- macOS: CoreBluetooth (device identifiers may be UUIDs).
- Windows: native BLE stack.
- Linux: BlueZ (you may need permissions for BLE access).

## Limitations

Command writes (e.g., set temp/smoke) are experimental and likely to be unreliable.
