"""GameCube GX texture pixel formats.

Textures are stored as tiles ("blocks") of format-specific dimensions, tiles
in row-major order, pixels row-major within a tile, everything big-endian.
Decoding always produces RGBA8888 bytes, row-major, 4 bytes per pixel.

Formats (GX enum values):
  0 I4      8x8 tiles, 4bpp intensity
  1 I8      8x4 tiles, 8bpp intensity
  2 IA4     8x4 tiles, 8bpp: low nibble intensity, high nibble alpha
  3 IA8     4x4 tiles, 16bpp: alpha byte then intensity byte
  4 RGB565  4x4 tiles, 16bpp
  5 RGB5A3  4x4 tiles, 16bpp: MSB set = opaque RGB555, clear = A3+RGB444
  6 RGBA32  4x4 tiles, 64 bytes: 32 bytes of AR pairs then 32 of GB pairs
  14 CMPR   8x8 tiles of four DXT1-style 4x4 sub-blocks (BE colors,
            MSB-first index bits)

Palette formats (C4/C8/C14X2) are not implemented yet.
"""

from __future__ import annotations

import struct

FORMAT_NAMES = {
    0: "I4", 1: "I8", 2: "IA4", 3: "IA8", 4: "RGB565", 5: "RGB5A3",
    6: "RGBA32", 8: "C4", 9: "C8", 10: "C14X2", 14: "CMPR",
}
NAME_TO_FORMAT = {v: k for k, v in FORMAT_NAMES.items()}

# format -> (tile_width, tile_height, bytes_per_tile)
TILE_SPECS = {
    0: (8, 8, 32),
    1: (8, 4, 32),
    2: (8, 4, 32),
    3: (4, 4, 32),
    4: (4, 4, 32),
    5: (4, 4, 32),
    6: (4, 4, 64),
    14: (8, 8, 32),
}

ENCODABLE = {0, 1, 2, 3, 4, 5, 6}


def _expand5(v: int) -> int:
    return (v << 3) | (v >> 2)


def _expand4(v: int) -> int:
    return v * 0x11


def _expand3(v: int) -> int:
    return (v << 5) | (v << 2) | (v >> 1)


def _rgb565(value: int) -> tuple[int, int, int]:
    return (
        _expand5(value >> 11),
        (value >> 5 & 0x3F) << 2 | (value >> 5 & 0x3F) >> 4,
        _expand5(value & 0x1F),
    )


def encoded_size(fmt: int, width: int, height: int) -> int:
    tw, th, tbytes = TILE_SPECS[fmt]
    tiles_x = (width + tw - 1) // tw
    tiles_y = (height + th - 1) // th
    return tiles_x * tiles_y * tbytes


def decode(fmt: int, width: int, height: int, data: bytes) -> bytes:
    """Decode texture data to RGBA8888 (row-major, 4 bytes/pixel)."""
    if fmt not in TILE_SPECS:
        name = FORMAT_NAMES.get(fmt, str(fmt))
        raise ValueError(f"unsupported texture format {name}")
    tw, th, tbytes = TILE_SPECS[fmt]
    if len(data) < encoded_size(fmt, width, height):
        raise ValueError("texture data truncated")

    out = bytearray(width * height * 4)

    def put(x: int, y: int, r: int, g: int, b: int, a: int) -> None:
        if x >= width or y >= height:
            return  # tile padding beyond image edge
        i = (y * width + x) * 4
        out[i : i + 4] = bytes((r, g, b, a))

    tiles_x = (width + tw - 1) // tw
    tiles_y = (height + th - 1) // th
    pos = 0
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            tile = data[pos : pos + tbytes]
            pos += tbytes
            ox, oy = tx * tw, ty * th
            if fmt == 0:  # I4
                for py in range(8):
                    for px in range(8):
                        nibble_index = py * 8 + px
                        byte = tile[nibble_index // 2]
                        v = byte >> 4 if nibble_index % 2 == 0 else byte & 0xF
                        i = _expand4(v)
                        put(ox + px, oy + py, i, i, i, 255)
            elif fmt == 1:  # I8
                for py in range(4):
                    for px in range(8):
                        i = tile[py * 8 + px]
                        put(ox + px, oy + py, i, i, i, 255)
            elif fmt == 2:  # IA4
                for py in range(4):
                    for px in range(8):
                        byte = tile[py * 8 + px]
                        i = _expand4(byte & 0xF)
                        a = _expand4(byte >> 4)
                        put(ox + px, oy + py, i, i, i, a)
            elif fmt == 3:  # IA8
                for py in range(4):
                    for px in range(4):
                        off = (py * 4 + px) * 2
                        a, i = tile[off], tile[off + 1]
                        put(ox + px, oy + py, i, i, i, a)
            elif fmt == 4:  # RGB565
                for py in range(4):
                    for px in range(4):
                        off = (py * 4 + px) * 2
                        (value,) = struct.unpack(">H", tile[off : off + 2])
                        r, g, b = _rgb565(value)
                        put(ox + px, oy + py, r, g, b, 255)
            elif fmt == 5:  # RGB5A3
                for py in range(4):
                    for px in range(4):
                        off = (py * 4 + px) * 2
                        (value,) = struct.unpack(">H", tile[off : off + 2])
                        if value & 0x8000:
                            r = _expand5(value >> 10 & 0x1F)
                            g = _expand5(value >> 5 & 0x1F)
                            b = _expand5(value & 0x1F)
                            a = 255
                        else:
                            a = _expand3(value >> 12 & 0x7)
                            r = _expand4(value >> 8 & 0xF)
                            g = _expand4(value >> 4 & 0xF)
                            b = _expand4(value & 0xF)
                        put(ox + px, oy + py, r, g, b, a)
            elif fmt == 6:  # RGBA32
                for py in range(4):
                    for px in range(4):
                        off = (py * 4 + px) * 2
                        a, r = tile[off], tile[off + 1]
                        g, b = tile[32 + off], tile[32 + off + 1]
                        put(ox + px, oy + py, r, g, b, a)
            elif fmt == 14:  # CMPR
                for sub in range(4):
                    sx, sy = (sub % 2) * 4, (sub // 2) * 4
                    block = tile[sub * 8 : sub * 8 + 8]
                    c0, c1, indices = struct.unpack(">HHI", block)
                    p = [_rgb565(c0) + (255,), _rgb565(c1) + (255,)]
                    if c0 > c1:
                        p.append(tuple(
                            (2 * p[0][i] + p[1][i]) // 3 for i in range(3)) + (255,))
                        p.append(tuple(
                            (p[0][i] + 2 * p[1][i]) // 3 for i in range(3)) + (255,))
                    else:
                        p.append(tuple(
                            (p[0][i] + p[1][i]) // 2 for i in range(3)) + (255,))
                        p.append((0, 0, 0, 0))
                    for py in range(4):
                        for px in range(4):
                            shift = 30 - (py * 4 + px) * 2  # MSB-first
                            r, g, b, a = p[indices >> shift & 0x3]
                            put(ox + sx + px, oy + sy + py, r, g, b, a)
    return bytes(out)


def encode(fmt: int, width: int, height: int, rgba: bytes) -> bytes:
    """Encode RGBA8888 pixels into a GX texture format (CMPR not supported)."""
    if fmt not in ENCODABLE:
        name = FORMAT_NAMES.get(fmt, str(fmt))
        raise ValueError(f"encoding to {name} is not supported")
    if len(rgba) != width * height * 4:
        raise ValueError("rgba buffer does not match dimensions")
    tw, th, tbytes = TILE_SPECS[fmt]

    def pixel(x: int, y: int) -> tuple[int, int, int, int]:
        if x >= width or y >= height:
            return 0, 0, 0, 0
        i = (y * width + x) * 4
        return rgba[i], rgba[i + 1], rgba[i + 2], rgba[i + 3]

    def intensity(r: int, g: int, b: int) -> int:
        return (r * 77 + g * 150 + b * 29) >> 8  # BT.601-ish luma

    out = bytearray()
    tiles_x = (width + tw - 1) // tw
    tiles_y = (height + th - 1) // th
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            ox, oy = tx * tw, ty * th
            tile = bytearray(tbytes)
            if fmt == 0:  # I4
                for py in range(8):
                    for px in range(8):
                        r, g, b, _ = pixel(ox + px, oy + py)
                        v = intensity(r, g, b) >> 4
                        idx = py * 8 + px
                        if idx % 2 == 0:
                            tile[idx // 2] |= v << 4
                        else:
                            tile[idx // 2] |= v
            elif fmt == 1:  # I8
                for py in range(4):
                    for px in range(8):
                        r, g, b, _ = pixel(ox + px, oy + py)
                        tile[py * 8 + px] = intensity(r, g, b)
            elif fmt == 2:  # IA4
                for py in range(4):
                    for px in range(8):
                        r, g, b, a = pixel(ox + px, oy + py)
                        tile[py * 8 + px] = (a >> 4) << 4 | intensity(r, g, b) >> 4
            elif fmt == 3:  # IA8
                for py in range(4):
                    for px in range(4):
                        r, g, b, a = pixel(ox + px, oy + py)
                        off = (py * 4 + px) * 2
                        tile[off] = a
                        tile[off + 1] = intensity(r, g, b)
            elif fmt == 4:  # RGB565
                for py in range(4):
                    for px in range(4):
                        r, g, b, _ = pixel(ox + px, oy + py)
                        value = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3
                        off = (py * 4 + px) * 2
                        tile[off : off + 2] = struct.pack(">H", value)
            elif fmt == 5:  # RGB5A3
                for py in range(4):
                    for px in range(4):
                        r, g, b, a = pixel(ox + px, oy + py)
                        if a >= 0xE0:
                            value = 0x8000 | (r >> 3) << 10 | (g >> 3) << 5 | b >> 3
                        else:
                            value = ((a >> 5) << 12 | (r >> 4) << 8
                                     | (g >> 4) << 4 | b >> 4)
                        off = (py * 4 + px) * 2
                        tile[off : off + 2] = struct.pack(">H", value)
            elif fmt == 6:  # RGBA32
                for py in range(4):
                    for px in range(4):
                        r, g, b, a = pixel(ox + px, oy + py)
                        off = (py * 4 + px) * 2
                        tile[off], tile[off + 1] = a, r
                        tile[32 + off], tile[32 + off + 1] = g, b
            out += tile
    return bytes(out)
