#include "gcrt/hal.h"

#include <chrono>
#include <cstdio>
#include <thread>

namespace gcrt {

uint64_t NullHal::nowNs() {
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch())
            .count());
}

void NullHal::sleepNs(uint64_t ns) {
    if (real_sleep_) {
        std::this_thread::sleep_for(std::chrono::nanoseconds(ns));
    }
}

void NullHal::pollInput(PadInput out[4]) {
    for (int i = 0; i < 4; ++i) {
        out[i] = PadInput{};  // neutral, disconnected
    }
}

void NullHal::log(const char* message) {
    std::fprintf(stderr, "%s\n", message);
}

}  // namespace gcrt
