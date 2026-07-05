// Exercises SdlHal init/teardown and input polling using SDL's dummy video
// driver so it runs headlessly in CI.
#include <cstdio>
#include <cstdlib>

#include "gcrt/hal_sdl.h"

using namespace gcrt;

int main() {
    setenv("SDL_VIDEODRIVER", "dummy", 1);

    SdlHal::Options options;
    options.window_title = "gcrt sdl test";
    SdlHal hal(options);

    if (hal.window() == nullptr) {
        std::fprintf(stderr, "FAIL: no window created\n");
        return 1;
    }
    if (hal.quitRequested()) {
        std::fprintf(stderr, "FAIL: quit requested at startup\n");
        return 1;
    }

    uint64_t t0 = hal.nowNs();
    hal.sleepNs(1'000'000);  // 1 ms
    if (hal.nowNs() <= t0) {
        std::fprintf(stderr, "FAIL: clock not monotonic across sleep\n");
        return 1;
    }

    PadInput pads[4];
    for (int i = 0; i < 5; ++i) {
        hal.pollInput(pads);
    }
    for (int i = 0; i < 4; ++i) {
        // dummy driver: no controllers, no keys held
        if (pads[i].connected || pads[i].buttons != 0) {
            std::fprintf(stderr, "FAIL: pad %d not neutral\n", i);
            return 1;
        }
    }

    hal.log("gcrt sdl hal test: all checks passed");
    std::printf("gcrt sdl hal test: all checks passed\n");
    return 0;
}
