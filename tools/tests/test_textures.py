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
    header[0] = 7  # not a real GX texture format
    header[2:6] = struct.pack(">HH", 4, 4)
    with pytest.raises(ValueError):
        bti.Bti.parse(bytes(header))


def _make_paletted_bti(fmt, width, height, palette565, index_bytes):
    """Build a BTI with an RGB565 palette and raw index data (for tests)."""
    palette = b"".join(struct.pack(">H", v) for v in palette565)
    header = bytearray(bti.HEADER_SIZE)
    header[0] = fmt
    struct.pack_into(">HH", header, 2, width, height)
    header[0x09] = gx_texture.PALETTE_RGB565
    struct.pack_into(">H", header, 0x0A, len(palette565))    # palette count
    struct.pack_into(">I", header, 0x0C, bti.HEADER_SIZE)    # palette offset
    header[0x18] = 1                                          # 1 mipmap
    image_off = bti.HEADER_SIZE + len(palette)
    struct.pack_into(">I", header, 0x1C, image_off)          # image offset
    return bytes(header) + palette + bytes(index_bytes)


def test_c8_palette_decode():
    # palette: 0=red, 1=green, 2=blue; 8x4 = one C8 tile, indices per pixel
    palette = [0xF800, 0x07E0, 0x001F]
    indices = [(x + y) % 3 for y in range(4) for x in range(8)]
    blob = _make_paletted_bti(9, 8, 4, palette, indices)
    tex = bti.Bti.parse(blob)
    assert (tex.format, tex.width, tex.height) == (9, 8, 4)
    assert tex.rgba[0:4] == bytes((255, 0, 0, 255))   # pixel(0,0) index 0 red
    assert tex.rgba[4:8] == bytes((0, 255, 0, 255))   # pixel(1,0) index 1 green
    assert tex.rgba[8:12] == bytes((0, 0, 255, 255))  # pixel(2,0) index 2 blue


def test_c4_palette_decode():
    # C4: 8x8 tile, 4-bit indices packed two per byte (high nibble first)
    palette = [0xF800, 0x07E0]  # red, green
    # 64 indices alternating 0,1,0,1...
    idx = [(x + y) % 2 for y in range(8) for x in range(8)]
    packed = bytes((idx[i] << 4) | idx[i + 1] for i in range(0, 64, 2))
    blob = _make_paletted_bti(8, 8, 8, palette, packed)
    tex = bti.Bti.parse(blob)
    assert tex.rgba[0:4] == bytes((255, 0, 0, 255))   # index 0 red
    assert tex.rgba[4:8] == bytes((0, 255, 0, 255))   # index 1 green


def test_c14x2_palette_decode():
    # C14X2: 4x4 tile, 16-bit values, low 14 bits index the palette
    palette = [0] * 5
    palette[3] = 0x001F  # blue at index 3
    values = [3] + [0] * 15  # first pixel -> index 3
    data = b"".join(struct.pack(">H", v) for v in values)
    blob = _make_paletted_bti(10, 4, 4, palette, data)
    tex = bti.Bti.parse(blob)
    assert tex.rgba[0:4] == bytes((0, 0, 255, 255))   # blue


def test_paletted_requires_palette():
    # decoding an indexed format without a palette is an error, not a crash
    with pytest.raises(ValueError):
        gx_texture.decode(9, 8, 4, bytes(32))


def test_palette_entry_formats():
    # IA8 entry: high byte alpha, low byte intensity
    pal = gx_texture.decode_palette(struct.pack(">H", 0x80FF),
                                    gx_texture.PALETTE_IA8, 1)
    assert pal[0] == (255, 255, 255, 128)
