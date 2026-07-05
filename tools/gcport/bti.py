"""BTI texture container (GameCube first-party standalone texture files).

Header (0x20 bytes, big-endian):
  0x00 u8  texture format (GX enum, see gx_texture)
  0x01 u8  alpha enabled
  0x02 u16 width
  0x04 u16 height
  0x06 u8  wrap S, 0x07 u8 wrap T
  0x08 u8  palettes enabled, 0x09 u8 palette format, 0x0A u16 palette count
  0x0C u32 palette data offset
  0x10 u32 border color
  0x14 u8  min filter, 0x15 u8 mag filter
  0x16 u16 LOD bias
  0x18 u8  mipmap count, 0x19 u8 unknown, 0x1A u16 unknown
  0x1C u32 image data offset

Only mipmap level 0 is decoded; encoding writes a single level.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import gx_texture

HEADER_SIZE = 0x20


@dataclass
class Bti:
    format: int
    width: int
    height: int
    mipmap_count: int
    rgba: bytes  # level 0, decoded

    @classmethod
    def parse(cls, data: bytes) -> "Bti":
        if len(data) < HEADER_SIZE:
            raise ValueError("BTI too small")
        fmt = data[0]
        width, height = struct.unpack(">HH", data[2:6])
        mipmaps = data[0x18]
        (image_offset,) = struct.unpack(">I", data[0x1C:0x20])
        if fmt not in gx_texture.TILE_SPECS:
            name = gx_texture.FORMAT_NAMES.get(fmt, str(fmt))
            raise ValueError(f"BTI uses unsupported format {name}")
        size = gx_texture.encoded_size(fmt, width, height)
        payload = data[image_offset : image_offset + size]
        rgba = gx_texture.decode(fmt, width, height, payload)
        return cls(fmt, width, height, max(mipmaps, 1), rgba)

    def describe(self) -> str:
        name = gx_texture.FORMAT_NAMES.get(self.format, str(self.format))
        return (f"format      : {name}\n"
                f"size        : {self.width}x{self.height}\n"
                f"mipmaps     : {self.mipmap_count}")


def build(fmt: int, width: int, height: int, rgba: bytes) -> bytes:
    payload = gx_texture.encode(fmt, width, height, rgba)
    has_alpha = fmt in (2, 3, 5, 6)
    header = struct.pack(
        ">BBHHBB BBH I I BBH BBH I".replace(" ", ""),
        fmt, 1 if has_alpha else 0, width, height,
        1, 1,           # wrap S/T: repeat
        0, 0, 0,        # no palette
        0,              # palette offset
        0,              # border color
        1, 1, 0,        # min/mag filter: linear, LOD bias 0
        1, 0, 0,        # 1 mipmap level
        HEADER_SIZE,    # image data offset
    )
    return header + payload
