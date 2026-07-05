// GX texture pixel-format decode for the runtime. Mirrors gcport.gx_texture
// (the Python tool) so the same formats behave identically at build time and
// run time. Decodes to RGBA8888, row-major. See that module's docstring for
// the tile layout and format table.
#pragma once

#include <cstdint>
#include <vector>

namespace gcrt {

enum GXTexFmt : uint8_t {
    GX_TF_I4 = 0,
    GX_TF_I8 = 1,
    GX_TF_IA4 = 2,
    GX_TF_IA8 = 3,
    GX_TF_RGB565 = 4,
    GX_TF_RGB5A3 = 5,
    GX_TF_RGBA8 = 6,
    GX_TF_CMPR = 14,
};

// Bytes of encoded texture data for a format at the given dimensions.
size_t GXTexEncodedSize(GXTexFmt format, int width, int height);

// Decode to RGBA8888 (width*height*4 bytes). Throws std::invalid_argument on
// an unsupported format or truncated input.
std::vector<uint8_t> GXDecodeTexture(GXTexFmt format, int width, int height,
                                     const uint8_t* data, size_t size);

}  // namespace gcrt
