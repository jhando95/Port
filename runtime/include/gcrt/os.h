// Dolphin OS services: init, reporting, time, and the MEM1 arena allocator.
// Function names and semantics mirror the GameCube SDK so recompiled game
// code can link against them directly.
#pragma once

#include <cstddef>
#include <cstdint>

#include "gcrt/hal.h"

namespace gcrt {

constexpr size_t kMem1Size = 24 * 1024 * 1024;  // GameCube main memory
// GameCube time base: bus clock 162 MHz, OS tick = bus/4 = 40.5 MHz.
constexpr uint64_t kTicksPerSecond = 40500000;

struct RuntimeConfig {
    Hal* hal = nullptr;
    const char* asset_root = nullptr;  // extracted files/ directory
};

// Boots the runtime: arena, time base, subsystem state. Call once, first.
void OSInit(const RuntimeConfig& config);
void OSShutdown();

Hal& OSHal();
const char* OSAssetRoot();

void OSReport(const char* format, ...);

uint64_t OSGetTime();  // ticks since OSInit
uint32_t OSGetTick();
inline uint64_t OSTicksToMilliseconds(uint64_t ticks) {
    return ticks / (kTicksPerSecond / 1000);
}

// MEM1 arena. Recompiled code allocates its heaps from here.
void* OSGetArenaLo();
void* OSGetArenaHi();
void OSSetArenaLo(void* lo);
void OSSetArenaHi(void* hi);
void* OSAllocFromArenaLo(size_t size, size_t alignment);

}  // namespace gcrt
