// GX service: the GameCube's GPU command interface, implemented as a software
// rasterizer into an RGBA framebuffer (the "EFB"). Current scope: viewport,
// projection + modelview transforms, immediate-mode triangle submission with
// per-vertex colors, Gouraud shading, z-buffering, and copy-clear. Textures,
// TEV stages, and lighting come later; a GPU backend can replace the
// rasterizer behind the same API.
//
// Deviations from hardware, to revisit when recompiled code is integrated:
// no near-plane clipping (triangles with any w <= 0 are dropped whole), and
// depth is normalized to [0,1] rather than the GC's clip conventions.
#pragma once

#include <cstdint>

namespace gcrt {

struct GXColor {
    uint8_t r = 0, g = 0, b = 0, a = 255;
};

using Mtx = float[3][4];    // row-major 3x4, GC convention
using Mtx44 = float[4][4];  // row-major 4x4

enum GXPrimitive : uint8_t {
    GX_TRIANGLES = 0x90,
};

enum GXProjectionType : uint8_t {
    GX_PERSPECTIVE = 0,
    GX_ORTHOGRAPHIC = 1,
};

enum GXCompare : uint8_t {
    GX_NEVER, GX_LESS, GX_EQUAL, GX_LEQUAL,
    GX_GREATER, GX_NEQUAL, GX_GEQUAL, GX_ALWAYS,
};

// Framebuffer dimensions are configurable (hardware EFB is up to 640x528).
void GXInit(int width, int height);
void GXShutdown();

int GXFbWidth();
int GXFbHeight();
// RGBA8888, row-major, valid until GXShutdown. Rendering target.
const uint8_t* GXFramebuffer();

void GXSetViewport(float x, float y, float width, float height,
                   float near_z, float far_z);
void GXSetProjection(const Mtx44 matrix, GXProjectionType type);
void GXLoadPosMtxImm(const Mtx matrix, uint32_t id = 0);
void GXSetZMode(bool compare_enable, GXCompare func, bool update_enable);

void GXSetCopyClear(GXColor color, uint32_t z);
// Clears the EFB with the copy-clear color and resets the depth buffer.
void GXCopyClear();

// Immediate-mode submission: GXBegin, then vertex_count repetitions of
// GXPosition3f32 (starts a vertex) + optional GXColor4u8, then GXEnd.
void GXBegin(GXPrimitive primitive, int vertex_count);
void GXPosition3f32(float x, float y, float z);
void GXColor4u8(uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void GXEnd();

// Test/tooling helper: read one pixel (RGBA).
GXColor GXReadPixel(int x, int y);

}  // namespace gcrt
