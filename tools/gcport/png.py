"""Minimal PNG reader/writer (stdlib only) for texture tooling.

Writer emits 8-bit RGBA, non-interlaced. Reader accepts 8-bit RGB/RGBA,
non-interlaced, any standard filter — which covers this writer's output and
typical image-editor exports. Not a general-purpose PNG library.
"""

from __future__ import annotations

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload)))


def write(width: int, height: int, rgba: bytes) -> bytes:
    if len(rgba) != width * height * 4:
        raise ValueError("rgba buffer does not match dimensions")
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter: None
        raw += rgba[y * stride : (y + 1) * stride]
    return (SIGNATURE + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def read(data: bytes) -> tuple[int, int, bytes]:
    """Returns (width, height, rgba)."""
    if data[:8] != SIGNATURE:
        raise ValueError("not a PNG file")
    pos = 8
    width = height = 0
    channels = 0
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _comp, _filt, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if depth != 8 or color not in (2, 6) or interlace != 0:
                raise ValueError(
                    "unsupported PNG (need 8-bit RGB/RGBA, non-interlaced)"
                )
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat += payload
        elif kind == b"IEND":
            break
    if not width or not idat:
        raise ValueError("PNG missing IHDR or IDAT")

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    if len(raw) != (stride + 1) * height:
        raise ValueError("PNG data size mismatch")

    def paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        return b if pb <= pc else c

    previous = bytearray(stride)
    rgba = bytearray()
    for y in range(height):
        offset = y * (stride + 1)
        filter_type = raw[offset]
        line = bytearray(raw[offset + 1 : offset + 1 + stride])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = previous[i]
            c = previous[i - channels] if i >= channels else 0
            if filter_type == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filter_type == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filter_type == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filter_type == 4:
                line[i] = (line[i] + paeth(a, b, c)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"unknown PNG filter {filter_type}")
        previous = line
        if channels == 3:
            for i in range(0, stride, 3):
                rgba += line[i : i + 3]
                rgba.append(255)
        else:
            rgba += line
    return width, height, bytes(rgba)
