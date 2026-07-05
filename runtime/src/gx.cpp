#include "gcrt/gx.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>

namespace gcrt {
namespace {

struct Vertex {
    float x = 0, y = 0, z = 0;  // object space
    GXColor color;
};

struct GxState {
    int width = 0, height = 0;
    std::vector<uint8_t> framebuffer;  // RGBA
    std::vector<float> depth;          // [0,1], 1 = far

    float vp_x = 0, vp_y = 0, vp_w = 0, vp_h = 0;
    float vp_near = 0.0f, vp_far = 1.0f;

    Mtx44 projection = {{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 1}};
    Mtx modelview = {{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}};

    bool z_compare = true;
    bool z_update = true;
    GXCompare z_func = GX_LEQUAL;

    GXColor clear_color;

    // immediate-mode assembly
    bool in_begin = false;
    int expected_vertices = 0;
    GXColor current_color{255, 255, 255, 255};
    std::vector<Vertex> pending;
};

std::unique_ptr<GxState> g_gx;

GxState& state() {
    if (!g_gx) throw std::logic_error("gcrt: GXInit() has not been called");
    return *g_gx;
}

struct ScreenVertex {
    float x, y, z;   // screen space, depth in [0,1]
    float r, g, b, a;
};

bool depthPasses(GXCompare func, float incoming, float stored) {
    switch (func) {
        case GX_NEVER: return false;
        case GX_LESS: return incoming < stored;
        case GX_EQUAL: return incoming == stored;
        case GX_LEQUAL: return incoming <= stored;
        case GX_GREATER: return incoming > stored;
        case GX_NEQUAL: return incoming != stored;
        case GX_GEQUAL: return incoming >= stored;
        case GX_ALWAYS: return true;
    }
    return true;
}

// object space -> screen space; returns false if the vertex lands behind the
// projection (w <= 0), which drops the whole triangle (no clipping yet).
bool transform(const GxState& s, const Vertex& v, ScreenVertex* out) {
    // modelview (3x4): view = M * (x, y, z, 1)
    float vx = s.modelview[0][0] * v.x + s.modelview[0][1] * v.y +
               s.modelview[0][2] * v.z + s.modelview[0][3];
    float vy = s.modelview[1][0] * v.x + s.modelview[1][1] * v.y +
               s.modelview[1][2] * v.z + s.modelview[1][3];
    float vz = s.modelview[2][0] * v.x + s.modelview[2][1] * v.y +
               s.modelview[2][2] * v.z + s.modelview[2][3];

    const Mtx44& p = s.projection;
    float cx = p[0][0] * vx + p[0][1] * vy + p[0][2] * vz + p[0][3];
    float cy = p[1][0] * vx + p[1][1] * vy + p[1][2] * vz + p[1][3];
    float cz = p[2][0] * vx + p[2][1] * vy + p[2][2] * vz + p[2][3];
    float cw = p[3][0] * vx + p[3][1] * vy + p[3][2] * vz + p[3][3];
    if (cw <= 0.0f) return false;

    float ndc_x = cx / cw, ndc_y = cy / cw, ndc_z = cz / cw;
    out->x = s.vp_x + (ndc_x + 1.0f) * 0.5f * s.vp_w;
    out->y = s.vp_y + (1.0f - ndc_y) * 0.5f * s.vp_h;  // screen y grows down
    float depth01 = std::clamp(ndc_z * 0.5f + 0.5f, 0.0f, 1.0f);
    out->z = s.vp_near + depth01 * (s.vp_far - s.vp_near);
    out->r = v.color.r;
    out->g = v.color.g;
    out->b = v.color.b;
    out->a = v.color.a;
    return true;
}

float edge(const ScreenVertex& a, const ScreenVertex& b, float px, float py) {
    return (b.x - a.x) * (py - a.y) - (b.y - a.y) * (px - a.x);
}

void rasterize(GxState& s, ScreenVertex v0, ScreenVertex v1, ScreenVertex v2) {
    float area = edge(v0, v1, v2.x, v2.y);
    if (area == 0.0f) return;
    if (area < 0.0f) {  // accept both windings (cull mode: none)
        std::swap(v1, v2);
        area = -area;
    }

    int min_x = std::max(0, static_cast<int>(
                                std::floor(std::min({v0.x, v1.x, v2.x}))));
    int max_x = std::min(s.width - 1, static_cast<int>(std::ceil(
                                          std::max({v0.x, v1.x, v2.x}))));
    int min_y = std::max(0, static_cast<int>(
                                std::floor(std::min({v0.y, v1.y, v2.y}))));
    int max_y = std::min(s.height - 1, static_cast<int>(std::ceil(
                                           std::max({v0.y, v1.y, v2.y}))));

    for (int y = min_y; y <= max_y; ++y) {
        for (int x = min_x; x <= max_x; ++x) {
            float px = x + 0.5f, py = y + 0.5f;
            float w0 = edge(v1, v2, px, py);
            float w1 = edge(v2, v0, px, py);
            float w2 = edge(v0, v1, px, py);
            if (w0 < 0 || w1 < 0 || w2 < 0) continue;
            w0 /= area;
            w1 /= area;
            w2 /= area;

            float z = w0 * v0.z + w1 * v1.z + w2 * v2.z;
            size_t di = static_cast<size_t>(y) * s.width + x;
            if (s.z_compare && !depthPasses(s.z_func, z, s.depth[di])) {
                continue;
            }
            if (s.z_update) s.depth[di] = z;

            auto lerp = [&](float a, float b, float c) {
                return static_cast<uint8_t>(
                    std::clamp(w0 * a + w1 * b + w2 * c, 0.0f, 255.0f));
            };
            uint8_t* px_out = &s.framebuffer[di * 4];
            px_out[0] = lerp(v0.r, v1.r, v2.r);
            px_out[1] = lerp(v0.g, v1.g, v2.g);
            px_out[2] = lerp(v0.b, v1.b, v2.b);
            px_out[3] = lerp(v0.a, v1.a, v2.a);
        }
    }
}

void flushPrimitives(GxState& s) {
    for (size_t i = 0; i + 2 < s.pending.size(); i += 3) {
        ScreenVertex sv[3];
        bool visible = true;
        for (int j = 0; j < 3; ++j) {
            if (!transform(s, s.pending[i + j], &sv[j])) {
                visible = false;
                break;
            }
        }
        if (visible) rasterize(s, sv[0], sv[1], sv[2]);
    }
    s.pending.clear();
}

}  // namespace

void GXInit(int width, int height) {
    if (g_gx) throw std::logic_error("gcrt: GXInit() called twice");
    if (width <= 0 || height <= 0) {
        throw std::invalid_argument("gcrt: bad framebuffer size");
    }
    g_gx = std::make_unique<GxState>();
    g_gx->width = width;
    g_gx->height = height;
    g_gx->framebuffer.assign(static_cast<size_t>(width) * height * 4, 0);
    g_gx->depth.assign(static_cast<size_t>(width) * height, 1.0f);
    g_gx->vp_w = static_cast<float>(width);
    g_gx->vp_h = static_cast<float>(height);
}

void GXShutdown() { g_gx.reset(); }

int GXFbWidth() { return state().width; }
int GXFbHeight() { return state().height; }
const uint8_t* GXFramebuffer() { return state().framebuffer.data(); }

void GXSetViewport(float x, float y, float width, float height, float near_z,
                   float far_z) {
    auto& s = state();
    s.vp_x = x;
    s.vp_y = y;
    s.vp_w = width;
    s.vp_h = height;
    s.vp_near = near_z;
    s.vp_far = far_z;
}

void GXSetProjection(const Mtx44 matrix, GXProjectionType) {
    std::memcpy(state().projection, matrix, sizeof(Mtx44));
}

void GXLoadPosMtxImm(const Mtx matrix, uint32_t) {
    std::memcpy(state().modelview, matrix, sizeof(Mtx));
}

void GXSetZMode(bool compare_enable, GXCompare func, bool update_enable) {
    auto& s = state();
    s.z_compare = compare_enable;
    s.z_func = func;
    s.z_update = update_enable;
}

void GXSetCopyClear(GXColor color, uint32_t) { state().clear_color = color; }

void GXCopyClear() {
    auto& s = state();
    for (size_t i = 0; i < s.framebuffer.size(); i += 4) {
        s.framebuffer[i] = s.clear_color.r;
        s.framebuffer[i + 1] = s.clear_color.g;
        s.framebuffer[i + 2] = s.clear_color.b;
        s.framebuffer[i + 3] = s.clear_color.a;
    }
    std::fill(s.depth.begin(), s.depth.end(), 1.0f);
}

void GXBegin(GXPrimitive primitive, int vertex_count) {
    auto& s = state();
    if (s.in_begin) throw std::logic_error("gcrt: nested GXBegin");
    if (primitive != GX_TRIANGLES) {
        throw std::invalid_argument("gcrt: only GX_TRIANGLES implemented");
    }
    if (vertex_count % 3 != 0) {
        throw std::invalid_argument("gcrt: GX_TRIANGLES needs multiple of 3");
    }
    s.in_begin = true;
    s.expected_vertices = vertex_count;
    s.pending.clear();
}

void GXPosition3f32(float x, float y, float z) {
    auto& s = state();
    if (!s.in_begin) throw std::logic_error("gcrt: vertex outside GXBegin");
    Vertex v;
    v.x = x;
    v.y = y;
    v.z = z;
    v.color = s.current_color;
    s.pending.push_back(v);
}

void GXColor4u8(uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
    auto& s = state();
    s.current_color = GXColor{r, g, b, a};
    if (s.in_begin && !s.pending.empty()) {
        s.pending.back().color = s.current_color;  // color follows position
    }
}

void GXEnd() {
    auto& s = state();
    if (!s.in_begin) throw std::logic_error("gcrt: GXEnd outside GXBegin");
    if (static_cast<int>(s.pending.size()) != s.expected_vertices) {
        throw std::logic_error("gcrt: GXEnd vertex count mismatch");
    }
    s.in_begin = false;
    flushPrimitives(s);
}

GXColor GXReadPixel(int x, int y) {
    auto& s = state();
    if (x < 0 || y < 0 || x >= s.width || y >= s.height) {
        throw std::out_of_range("gcrt: GXReadPixel outside framebuffer");
    }
    const uint8_t* p = &s.framebuffer[(static_cast<size_t>(y) * s.width + x) * 4];
    return GXColor{p[0], p[1], p[2], p[3]};
}

}  // namespace gcrt
