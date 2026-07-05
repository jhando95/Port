#include "gcrt/gx_texture.h"

#include <stdexcept>

namespace gcrt {
namespace {

struct TileSpec {
    int tile_w, tile_h, tile_bytes;
    bool supported;
};

TileSpec specOf(GXTexFmt fmt) {
    switch (fmt) {
        case GX_TF_I4: return {8, 8, 32, true};
        case GX_TF_I8: return {8, 4, 32, true};
        case GX_TF_IA4: return {8, 4, 32, true};
        case GX_TF_IA8: return {4, 4, 32, true};
        case GX_TF_RGB565: return {4, 4, 32, true};
        case GX_TF_RGB5A3: return {4, 4, 32, true};
        case GX_TF_RGBA8: return {4, 4, 64, true};
        case GX_TF_CMPR: return {8, 8, 32, true};
        default: return {0, 0, 0, false};
    }
}

inline uint8_t expand5(uint8_t v) { return (v << 3) | (v >> 2); }
inline uint8_t expand4(uint8_t v) { return v * 0x11; }
inline uint8_t expand3(uint8_t v) { return (v << 5) | (v << 2) | (v >> 1); }
inline uint8_t expand6(uint8_t v) { return (v << 2) | (v >> 4); }

struct Rgb {
    uint8_t r, g, b;
};

Rgb rgb565(uint16_t value) {
    return {expand5(value >> 11), expand6((value >> 5) & 0x3F),
            expand5(value & 0x1F)};
}

}  // namespace

size_t GXTexEncodedSize(GXTexFmt format, int width, int height) {
    TileSpec spec = specOf(format);
    if (!spec.supported) return 0;
    int tiles_x = (width + spec.tile_w - 1) / spec.tile_w;
    int tiles_y = (height + spec.tile_h - 1) / spec.tile_h;
    return static_cast<size_t>(tiles_x) * tiles_y * spec.tile_bytes;
}

std::vector<uint8_t> GXDecodeTexture(GXTexFmt format, int width, int height,
                                     const uint8_t* data, size_t size) {
    TileSpec spec = specOf(format);
    if (!spec.supported) {
        throw std::invalid_argument("gcrt: unsupported texture format");
    }
    if (size < GXTexEncodedSize(format, width, height)) {
        throw std::invalid_argument("gcrt: texture data truncated");
    }

    std::vector<uint8_t> out(static_cast<size_t>(width) * height * 4, 0);
    auto put = [&](int x, int y, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
        if (x >= width || y >= height) return;
        size_t i = (static_cast<size_t>(y) * width + x) * 4;
        out[i] = r;
        out[i + 1] = g;
        out[i + 2] = b;
        out[i + 3] = a;
    };

    int tiles_x = (width + spec.tile_w - 1) / spec.tile_w;
    int tiles_y = (height + spec.tile_h - 1) / spec.tile_h;
    size_t pos = 0;
    for (int ty = 0; ty < tiles_y; ++ty) {
        for (int tx = 0; tx < tiles_x; ++tx) {
            const uint8_t* tile = data + pos;
            pos += spec.tile_bytes;
            int ox = tx * spec.tile_w, oy = ty * spec.tile_h;
            switch (format) {
                case GX_TF_I4:
                    for (int py = 0; py < 8; ++py)
                        for (int px = 0; px < 8; ++px) {
                            int ni = py * 8 + px;
                            uint8_t byte = tile[ni / 2];
                            uint8_t v = (ni % 2 == 0) ? (byte >> 4) : (byte & 0xF);
                            uint8_t i = expand4(v);
                            put(ox + px, oy + py, i, i, i, 255);
                        }
                    break;
                case GX_TF_I8:
                    for (int py = 0; py < 4; ++py)
                        for (int px = 0; px < 8; ++px) {
                            uint8_t i = tile[py * 8 + px];
                            put(ox + px, oy + py, i, i, i, 255);
                        }
                    break;
                case GX_TF_IA4:
                    for (int py = 0; py < 4; ++py)
                        for (int px = 0; px < 8; ++px) {
                            uint8_t byte = tile[py * 8 + px];
                            uint8_t i = expand4(byte & 0xF);
                            uint8_t a = expand4(byte >> 4);
                            put(ox + px, oy + py, i, i, i, a);
                        }
                    break;
                case GX_TF_IA8:
                    for (int py = 0; py < 4; ++py)
                        for (int px = 0; px < 4; ++px) {
                            int off = (py * 4 + px) * 2;
                            uint8_t a = tile[off], i = tile[off + 1];
                            put(ox + px, oy + py, i, i, i, a);
                        }
                    break;
                case GX_TF_RGB565:
                    for (int py = 0; py < 4; ++py)
                        for (int px = 0; px < 4; ++px) {
                            int off = (py * 4 + px) * 2;
                            uint16_t value = (tile[off] << 8) | tile[off + 1];
                            Rgb c = rgb565(value);
                            put(ox + px, oy + py, c.r, c.g, c.b, 255);
                        }
                    break;
                case GX_TF_RGB5A3:
                    for (int py = 0; py < 4; ++py)
                        for (int px = 0; px < 4; ++px) {
                            int off = (py * 4 + px) * 2;
                            uint16_t value = (tile[off] << 8) | tile[off + 1];
                            uint8_t r, g, b, a;
                            if (value & 0x8000) {
                                r = expand5((value >> 10) & 0x1F);
                                g = expand5((value >> 5) & 0x1F);
                                b = expand5(value & 0x1F);
                                a = 255;
                            } else {
                                a = expand3((value >> 12) & 0x7);
                                r = expand4((value >> 8) & 0xF);
                                g = expand4((value >> 4) & 0xF);
                                b = expand4(value & 0xF);
                            }
                            put(ox + px, oy + py, r, g, b, a);
                        }
                    break;
                case GX_TF_RGBA8:
                    for (int py = 0; py < 4; ++py)
                        for (int px = 0; px < 4; ++px) {
                            int off = (py * 4 + px) * 2;
                            uint8_t a = tile[off], r = tile[off + 1];
                            uint8_t g = tile[32 + off], b = tile[32 + off + 1];
                            put(ox + px, oy + py, r, g, b, a);
                        }
                    break;
                case GX_TF_CMPR:
                    for (int sub = 0; sub < 4; ++sub) {
                        int sx = (sub % 2) * 4, sy = (sub / 2) * 4;
                        const uint8_t* block = tile + sub * 8;
                        uint16_t c0 = (block[0] << 8) | block[1];
                        uint16_t c1 = (block[2] << 8) | block[3];
                        uint32_t indices = (block[4] << 24) | (block[5] << 16) |
                                           (block[6] << 8) | block[7];
                        Rgb p[4];
                        uint8_t pa[4] = {255, 255, 255, 255};
                        p[0] = rgb565(c0);
                        p[1] = rgb565(c1);
                        if (c0 > c1) {
                            p[2] = {static_cast<uint8_t>((2 * p[0].r + p[1].r) / 3),
                                    static_cast<uint8_t>((2 * p[0].g + p[1].g) / 3),
                                    static_cast<uint8_t>((2 * p[0].b + p[1].b) / 3)};
                            p[3] = {static_cast<uint8_t>((p[0].r + 2 * p[1].r) / 3),
                                    static_cast<uint8_t>((p[0].g + 2 * p[1].g) / 3),
                                    static_cast<uint8_t>((p[0].b + 2 * p[1].b) / 3)};
                        } else {
                            p[2] = {static_cast<uint8_t>((p[0].r + p[1].r) / 2),
                                    static_cast<uint8_t>((p[0].g + p[1].g) / 2),
                                    static_cast<uint8_t>((p[0].b + p[1].b) / 2)};
                            p[3] = {0, 0, 0};
                            pa[3] = 0;
                        }
                        for (int py = 0; py < 4; ++py)
                            for (int px = 0; px < 4; ++px) {
                                int shift = 30 - (py * 4 + px) * 2;
                                int idx = (indices >> shift) & 0x3;
                                put(ox + sx + px, oy + sy + py, p[idx].r,
                                    p[idx].g, p[idx].b, pa[idx]);
                            }
                    }
                    break;
            }
        }
    }
    return out;
}

}  // namespace gcrt
