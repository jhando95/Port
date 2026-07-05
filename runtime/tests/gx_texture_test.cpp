// Verifies the runtime texture decoder against hand-computed expected values
// for each supported format. Parity with the Python decoder (gcport) is what
// lets build-time and run-time texture handling stay consistent.
#include <cstdint>
#include <cstdio>
#include <vector>

#include "gcrt/gx_texture.h"

using namespace gcrt;

namespace {

int g_failures = 0;

#define CHECK(cond)                                                      \
    do {                                                                 \
        if (!(cond)) {                                                   \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, \
                         #cond);                                         \
            ++g_failures;                                                \
        }                                                                \
    } while (0)

bool texel(const std::vector<uint8_t>& rgba, int w, int x, int y, uint8_t r,
           uint8_t g, uint8_t b, uint8_t a) {
    size_t i = (static_cast<size_t>(y) * w + x) * 4;
    return rgba[i] == r && rgba[i + 1] == g && rgba[i + 2] == b &&
           rgba[i + 3] == a;
}

}  // namespace

int main() {
    // RGBA8: one 4x4 tile, 32 bytes AR pairs then 32 bytes GB pairs.
    {
        std::vector<uint8_t> tile(64, 0);
        // texel (0,0): A=255 R=10, G=20 B=30
        tile[0] = 255;
        tile[1] = 10;
        tile[32] = 20;
        tile[33] = 30;
        auto out = GXDecodeTexture(GX_TF_RGBA8, 4, 4, tile.data(), tile.size());
        CHECK(texel(out, 4, 0, 0, 10, 20, 30, 255));
    }

    // RGB565: pure green 0x07E0 -> (0, 255, 0).
    {
        std::vector<uint8_t> tile(32, 0);
        tile[0] = 0x07;
        tile[1] = 0xE0;
        auto out = GXDecodeTexture(GX_TF_RGB565, 4, 4, tile.data(), tile.size());
        CHECK(texel(out, 4, 0, 0, 0, 255, 0, 255));
    }

    // RGB5A3 translucent: high bit clear, A3=3, R4=1,G4=2,B4=3.
    {
        std::vector<uint8_t> tile(32, 0);
        uint16_t v = (3 << 12) | (1 << 8) | (2 << 4) | 3;
        tile[0] = v >> 8;
        tile[1] = v & 0xFF;
        auto out = GXDecodeTexture(GX_TF_RGB5A3, 4, 4, tile.data(), tile.size());
        // A3=3 -> (3<<5)|(3<<2)|(3>>1) = 96+12+1 = 109; R4 1 -> 0x11 etc.
        CHECK(texel(out, 4, 0, 0, 0x11, 0x22, 0x33, 109));
    }

    // I8 grayscale.
    {
        std::vector<uint8_t> tile(32, 0);
        tile[0] = 128;
        auto out = GXDecodeTexture(GX_TF_I8, 8, 4, tile.data(), tile.size());
        CHECK(texel(out, 8, 0, 0, 128, 128, 128, 255));
    }

    // CMPR opaque mode (c0 > c1), all indices 0 -> c0.
    {
        std::vector<uint8_t> tile(32, 0);
        // sub-block 0: c0 = 0xF800 (red), c1 = 0x0000, indices 0
        tile[0] = 0xF8;
        tile[1] = 0x00;
        tile[2] = 0x00;
        tile[3] = 0x00;
        auto out = GXDecodeTexture(GX_TF_CMPR, 8, 8, tile.data(), tile.size());
        CHECK(texel(out, 8, 0, 0, 255, 0, 0, 255));
    }

    // Size accounting and truncation rejection.
    CHECK(GXTexEncodedSize(GX_TF_RGBA8, 4, 4) == 64);
    CHECK(GXTexEncodedSize(GX_TF_CMPR, 8, 8) == 32);
    CHECK(GXTexEncodedSize(GX_TF_RGB565, 5, 3) == 2 * 32);  // 2x1 tiles
    {
        std::vector<uint8_t> tiny(4, 0);
        bool threw = false;
        try {
            GXDecodeTexture(GX_TF_RGBA8, 4, 4, tiny.data(), tiny.size());
        } catch (const std::exception&) {
            threw = true;
        }
        CHECK(threw);
    }

    if (g_failures == 0) {
        std::printf("gcrt gx_texture test: all checks passed\n");
        return 0;
    }
    std::fprintf(stderr, "gcrt gx_texture test: %d failure(s)\n", g_failures);
    return 1;
}
