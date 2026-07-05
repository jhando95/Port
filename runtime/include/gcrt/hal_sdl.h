// SDL2-backed HAL: opens a window, maps keyboard + game controllers to
// GameCube pads, provides real-time pacing. Built when GCRT_WITH_SDL is on.
//
// Keyboard mapping (pad 0), Dolphin-style defaults:
//   arrows = main stick, X = A, Z = B, S = X, D = Y, Enter = Start,
//   Q/W = L/R triggers, C = Z. Game controllers map to pads 0-3 natively.
#pragma once

#include <cstdint>

#include "gcrt/hal.h"

struct SDL_Window;

namespace gcrt {

class SdlHal final : public Hal {
public:
    struct Options {
        const char* window_title = "gcrt";
        int width = 640;
        int height = 480;
        bool headless = false;  // no window; input from controllers only
    };

    explicit SdlHal(const Options& options);
    ~SdlHal() override;

    SdlHal(const SdlHal&) = delete;
    SdlHal& operator=(const SdlHal&) = delete;

    uint64_t nowNs() override;
    void sleepNs(uint64_t ns) override;
    void pollInput(PadInput out[4]) override;
    void log(const char* message) override;

    // True once the user closed the window or pressed Escape.
    bool quitRequested() const { return quit_requested_; }
    SDL_Window* window() const { return window_; }

private:
    SDL_Window* window_ = nullptr;
    bool quit_requested_ = false;
};

}  // namespace gcrt
