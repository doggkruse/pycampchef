from __future__ import annotations

from typing import Optional


def encode_mode_payload(
    mode_code: int,
    *,
    set_temp_f: Optional[int] = None,
    smoke_level: Optional[int] = None,
    fan_level: Optional[int] = None,
    extra: bytes = b"",
) -> bytes:
    data = bytearray([mode_code])
    if mode_code == 0x11:
        if set_temp_f is None or smoke_level is None:
            raise ValueError("set_temp_f and smoke_level are required for RUN mode")
        data += int(set_temp_f).to_bytes(2, byteorder="big", signed=True)
        data.append(int(smoke_level) & 0xFF)
    elif mode_code == 0x01:
        if fan_level is None:
            raise ValueError("fan_level is required for FAN mode")
        data.append(int(fan_level) & 0xFF)
    data += extra
    return bytes(data)
