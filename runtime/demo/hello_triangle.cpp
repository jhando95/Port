// First visible output from the gcrt runtime: a spinning Gouraud-shaded
// triangle rendered by the GX software rasterizer, presented in an SDL
// window, paced by VIWaitForRetrace — the same loop shape a real game uses.
//
// Set GCRT_DEMO_FRAMES=<n> to exit after n frames (used by CI, headless).
#include <SDL.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "gcrt/gx.h"
#include "gcrt/hal_sdl.h"
#include "gcrt/os.h"
#include "gcrt/pad.h"
#include "gcrt/vi.h"

using namespace gcrt;

int main() {
    const int width = 640, height = 480;

    SdlHal::Options options;
    options.window_title = "gcrt: hello triangle";
    options.width = width;
    options.height = height;
    SdlHal hal(options);

    RuntimeConfig config;
    config.hal = &hal;
    OSInit(config);
    GXInit(width, height);
    VIInit();
    PADInit();

    long max_frames = -1;
    if (const char* env = std::getenv("GCRT_DEMO_FRAMES")) {
        max_frames = std::strtol(env, nullptr, 10);
        VISetFrameRateForTesting(0);  // run unpaced when frame-bounded
    }

    SDL_Renderer* renderer =
        SDL_CreateRenderer(hal.window(), -1, SDL_RENDERER_ACCELERATED |
                                                  SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) renderer = SDL_CreateRenderer(hal.window(), -1, 0);
    SDL_Texture* texture =
        SDL_CreateTexture(renderer, SDL_PIXELFORMAT_RGBA32,
                          SDL_TEXTUREACCESS_STREAMING, width, height);
    if (!renderer || !texture) {
        std::fprintf(stderr, "SDL renderer setup failed: %s\n", SDL_GetError());
        return 1;
    }

    GXSetViewport(0, 0, static_cast<float>(width), static_cast<float>(height),
                  0.0f, 1.0f);
    Mtx44 identity = {{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 1}};
    GXSetProjection(identity, GX_ORTHOGRAPHIC);
    GXSetCopyClear(GXColor{18, 18, 28, 255}, 0);
    GXSetZMode(true, GX_LEQUAL, true);

    OSReport("hello_triangle: booted, entering main loop");

    PADStatus pads[kPadChannels];
    long frame = 0;
    while (!hal.quitRequested() && (max_frames < 0 || frame < max_frames)) {
        PADRead(pads);

        float angle = static_cast<float>(frame) * 0.02f;
        // rotate around z, slight squash for a 3/4 aspect feel
        Mtx rot = {
            {std::cos(angle), -std::sin(angle) * 0.75f, 0, 0},
            {std::sin(angle), std::cos(angle) * 0.75f, 0, 0},
            {0, 0, 1, 0},
        };
        GXLoadPosMtxImm(rot);

        GXCopyClear();
        GXBegin(GX_TRIANGLES, 3);
        GXPosition3f32(0.0f, 0.7f, 0.0f);
        GXColor4u8(255, 60, 60, 255);
        GXPosition3f32(-0.65f, -0.5f, 0.0f);
        GXColor4u8(60, 255, 60, 255);
        GXPosition3f32(0.65f, -0.5f, 0.0f);
        GXColor4u8(60, 60, 255, 255);
        GXEnd();

        SDL_UpdateTexture(texture, nullptr, GXFramebuffer(), width * 4);
        SDL_RenderClear(renderer);
        SDL_RenderCopy(renderer, texture, nullptr, nullptr);
        SDL_RenderPresent(renderer);

        VIWaitForRetrace();
        ++frame;
    }

    OSReport("hello_triangle: exiting after %ld frames "
             "(%u retraces)", frame, VIGetRetraceCount());

    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    GXShutdown();
    OSShutdown();
    return 0;
}
