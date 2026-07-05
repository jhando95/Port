// Pixel-level tests for the GX software rasterizer.
#include <cstdio>

#include "gcrt/gx.h"

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

bool colorEquals(GXColor c, uint8_t r, uint8_t g, uint8_t b) {
    return c.r == r && c.g == g && c.b == b;
}

// identity projection: NDC passthrough
constexpr Mtx44 kIdentity44 = {
    {1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 1}};
constexpr Mtx kIdentity34 = {{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}};

void drawTriangle(float verts[3][3], GXColor color) {
    GXBegin(GX_TRIANGLES, 3);
    for (int i = 0; i < 3; ++i) {
        GXPosition3f32(verts[i][0], verts[i][1], verts[i][2]);
        GXColor4u8(color.r, color.g, color.b, color.a);
    }
    GXEnd();
}

}  // namespace

int main() {
    GXInit(64, 64);
    GXSetViewport(0, 0, 64, 64, 0.0f, 1.0f);
    GXSetProjection(kIdentity44, GX_ORTHOGRAPHIC);
    GXLoadPosMtxImm(kIdentity34);

    // --- clear ------------------------------------------------------------
    GXSetCopyClear(GXColor{10, 20, 30, 255}, 0);
    GXCopyClear();
    CHECK(colorEquals(GXReadPixel(0, 0), 10, 20, 30));
    CHECK(colorEquals(GXReadPixel(63, 63), 10, 20, 30));

    // --- full-screen-ish triangle covers the center -------------------------
    float big[3][3] = {{-1, -1, 0}, {3, -1, 0}, {-1, 3, 0}};
    drawTriangle(big, GXColor{200, 0, 0, 255});
    CHECK(colorEquals(GXReadPixel(32, 32), 200, 0, 0));
    CHECK(colorEquals(GXReadPixel(1, 1), 200, 0, 0));

    // --- small triangle in the top-left quadrant (NDC +y is up) ------------
    GXCopyClear();
    float small_tri[3][3] = {{-0.9f, 0.9f, 0}, {-0.1f, 0.9f, 0}, {-0.9f, 0.1f, 0}};
    drawTriangle(small_tri, GXColor{0, 255, 0, 255});
    CHECK(colorEquals(GXReadPixel(8, 8), 0, 255, 0));      // inside
    CHECK(colorEquals(GXReadPixel(56, 56), 10, 20, 30));   // opposite corner
    CHECK(colorEquals(GXReadPixel(32, 8), 10, 20, 30));    // beyond the triangle's x extent

    // --- reversed winding still draws (cull none) ---------------------------
    GXCopyClear();
    float rev[3][3] = {{-0.9f, 0.1f, 0}, {-0.1f, 0.9f, 0}, {-0.9f, 0.9f, 0}};
    drawTriangle(rev, GXColor{0, 0, 250, 255});
    CHECK(colorEquals(GXReadPixel(8, 8), 0, 0, 250));

    // --- depth test: nearer triangle wins, farther is rejected -------------
    GXCopyClear();
    GXSetZMode(true, GX_LEQUAL, true);
    float near_tri[3][3] = {{-1, -1, -0.5f}, {3, -1, -0.5f}, {-1, 3, -0.5f}};
    float far_tri[3][3] = {{-1, -1, 0.5f}, {3, -1, 0.5f}, {-1, 3, 0.5f}};
    drawTriangle(near_tri, GXColor{255, 255, 255, 255});
    drawTriangle(far_tri, GXColor{40, 40, 40, 255});
    CHECK(colorEquals(GXReadPixel(32, 32), 255, 255, 255));

    // with depth compare off, the far triangle paints over
    GXSetZMode(false, GX_ALWAYS, false);
    drawTriangle(far_tri, GXColor{40, 40, 40, 255});
    CHECK(colorEquals(GXReadPixel(32, 32), 40, 40, 40));

    // --- Gouraud interpolation: distinct vertex colors blend ----------------
    GXSetZMode(true, GX_LEQUAL, true);
    GXCopyClear();
    GXBegin(GX_TRIANGLES, 3);
    GXPosition3f32(-1, -1, 0);
    GXColor4u8(255, 0, 0, 255);
    GXPosition3f32(3, -1, 0);
    GXColor4u8(0, 255, 0, 255);
    GXPosition3f32(-1, 3, 0);
    GXColor4u8(0, 0, 255, 255);
    GXEnd();
    GXColor center = GXReadPixel(32, 32);
    CHECK(center.r > 20 && center.g > 20 && center.b > 20);  // a mix
    CHECK(center.r < 220 && center.g < 220 && center.b < 220);

    // --- modelview translation moves geometry -------------------------------
    GXCopyClear();
    Mtx shift = {{1, 0, 0, 1.0f}, {0, 1, 0, 0}, {0, 0, 1, 0}};  // +1 in x
    GXLoadPosMtxImm(shift);
    float left[3][3] = {{-1.9f, 0.9f, 0}, {-1.1f, 0.9f, 0}, {-1.9f, 0.1f, 0}};
    drawTriangle(left, GXColor{255, 128, 0, 255});
    CHECK(colorEquals(GXReadPixel(8, 8), 255, 128, 0));  // shifted into view

    GXShutdown();

    if (g_failures == 0) {
        std::printf("gcrt gx test: all checks passed\n");
        return 0;
    }
    std::fprintf(stderr, "gcrt gx test: %d failure(s)\n", g_failures);
    return 1;
}
