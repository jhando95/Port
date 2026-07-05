import struct

import pytest

from gcport import bti, gx_texture, png


def checkerboard(width, height, colors):
    rgba = bytearray()
    for y in range(height):
        for x in range(width):
            rgba += bytes(colors[(x + y) % len(colors)])
    return bytes(rgba)


OPAQUE = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (16, 32, 48, 255)]


def test_rgba32_lossless_roundtrip():
    rgba = checkerboard(8, 8, [(1, 2, 3, 4), (250, 200, 150, 100)])
    encoded = gx_texture.encode(6, 8, 8, rgba)
    assert gx_texture.decode(6, 8, 8, encoded) == rgba


def test_rgb5a3_opaque_exact_values():
    # low multiples of 8 are fixed points of the 5->8 bit expansion
    colors = [(8, 16, 24, 255), (0, 8, 16, 255)]
    rgba = checkerboard(4, 4, colors)
    out = gx_texture.decode(5, 4, 4, gx_texture.encode(5, 4, 4, rgba))
    assert out == rgba


def test_rgb5a3_quantization_idempotent():
    # arbitrary colors: one encode/decode pass quantizes; a second is a no-op
    rgba = checkerboard(4, 4, [(13, 77, 201, 255), (249, 3, 128, 255)])
    once = gx_texture.decode(5, 4, 4, gx_texture.encode(5, 4, 4, rgba))
    twice = gx_texture.decode(5, 4, 4, gx_texture.encode(5, 4, 4, once))
    assert once == twice


def test_rgb5a3_translucent_pixel():
    # alpha 96 -> 3-bit 3 -> expands to 0x6D; RGB in 16-steps stays exact
    rgba = bytes((16, 32, 48, 96)) * 16
    out = gx_texture.decode(5, 4, 4, gx_texture.encode(5, 4, 4, rgba))
    r, g, b, a = out[0], out[1], out[2], out[3]
    assert (r, g, b) == (17, 34, 51)  # 4-bit expand of 1,2,3
    assert a == gx_texture._expand3(96 >> 5)


def test_i8_grayscale_roundtrip():
    rgba = checkerboard(8, 4, [(0, 0, 0, 255), (255, 255, 255, 255)])
    out = gx_texture.decode(1, 8, 4, gx_texture.encode(1, 8, 4, rgba))
    assert out == rgba


def test_ia8_alpha_roundtrip():
    rgba = checkerboard(4, 4, [(255, 255, 255, 0), (0, 0, 0, 255)])
    out = gx_texture.decode(3, 4, 4, gx_texture.encode(3, 4, 4, rgba))
    assert out == rgba


def test_rgb565_known_block():
    # single 4x4 tile, all pixels pure red (0xF800)
    tile = struct.pack(">H", 0xF800) * 16
    out = gx_texture.decode(4, 4, 4, tile)
    assert out[:4] == bytes((255, 0, 0, 255))


def test_nonaligned_dimensions_pad():
    # 5x3 RGB565 image occupies one 4x4 tile... no: 2x1 tiles
    rgba = checkerboard(5, 3, OPAQUE)
    encoded = gx_texture.encode(4, 5, 3, rgba)
    assert len(encoded) == gx_texture.encoded_size(4, 5, 3) == 2 * 32
    out = gx_texture.decode(4, 5, 3, encoded)
    assert len(out) == 5 * 3 * 4


def test_cmpr_decode_solid_subblock():
    # c0 > c1 selects the 4-color opaque palette; all indices 0 -> c0 color
    c0, c1 = 0xF800, 0x0000  # red, black
    sub = struct.pack(">HHI", c0, c1, 0)
    tile = sub * 4  # four identical 4x4 sub-blocks = 8x8 tile
    out = gx_texture.decode(14, 8, 8, tile)
    for i in range(0, len(out), 4):
        assert out[i : i + 4] == bytes((255, 0, 0, 255))


def test_cmpr_transparent_mode():
    # c0 <= c1: index 3 is transparent black
    sub = struct.pack(">HHI", 0x0000, 0xFFFF, 0xFFFFFFFF)
    tile = sub * 4
    out = gx_texture.decode(14, 8, 8, tile)
    assert out[3] == 0  # alpha


def test_cmpr_index_bit_order():
    # rows: pixel 0 uses the highest 2 bits of each row byte
    c0, c1 = 0xF800, 0x001F  # red, blue (c0 > c1)
    indices = 0b01_00_00_00_00000000_00000000_00000000  # pixel 0 -> c1? no:
    # byte 0 = row 0; MSB-first: pixel0 = bits 7-6 = 01 -> palette[1] = blue
    sub = struct.pack(">HHI", c0, c1, indices << 0)
    out = gx_texture.decode(14, 8, 8, sub * 4)
    assert out[0:4] == bytes((0, 0, 255, 255))    # pixel (0,0) blue
    assert out[4:8] == bytes((255, 0, 0, 255))    # pixel (1,0) red


def test_png_roundtrip():
    rgba = checkerboard(13, 7, [(9, 8, 7, 6), (200, 100, 50, 255)])
    data = png.write(13, 7, rgba)
    w, h, out = png.read(data)
    assert (w, h) == (13, 7)
    assert out == rgba


def test_png_rejects_garbage():
    with pytest.raises(ValueError):
        png.read(b"not a png at all")


def test_bti_roundtrip():
    rgba = checkerboard(16, 8, [(1, 2, 3, 4), (250, 200, 150, 100)])
    blob = bti.build(6, 16, 8, rgba)  # RGBA32 is lossless
    tex = bti.Bti.parse(blob)
    assert (tex.format, tex.width, tex.height) == (6, 16, 8)
    assert tex.rgba == rgba


def test_bti_rejects_unknown_format():
    header = bytearray(bti.HEADER_SIZE)
    header[0] = 9  # C8, palette format, unimplemented
    header[2:6] = struct.pack(">HH", 4, 4)
    with pytest.raises(ValueError):
        bti.Bti.parse(bytes(header))
