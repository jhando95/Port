#include "gcrt/os.h"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>

namespace gcrt {
namespace {

struct OsState {
    RuntimeConfig config;
    uint64_t boot_ns = 0;
    std::vector<uint8_t> mem1;
    uint8_t* arena_lo = nullptr;
    uint8_t* arena_hi = nullptr;
};

std::unique_ptr<OsState> g_os;

OsState& state() {
    if (!g_os) {
        throw std::logic_error("gcrt: OSInit() has not been called");
    }
    return *g_os;
}

}  // namespace

void OSInit(const RuntimeConfig& config) {
    if (g_os) {
        throw std::logic_error("gcrt: OSInit() called twice");
    }
    if (!config.hal) {
        throw std::invalid_argument("gcrt: RuntimeConfig.hal is required");
    }
    g_os = std::make_unique<OsState>();
    g_os->config = config;
    g_os->boot_ns = config.hal->nowNs();
    g_os->mem1.resize(kMem1Size);
    g_os->arena_lo = g_os->mem1.data();
    g_os->arena_hi = g_os->mem1.data() + g_os->mem1.size();
}

void OSShutdown() { g_os.reset(); }

Hal& OSHal() { return *state().config.hal; }

const char* OSAssetRoot() { return state().config.asset_root; }

void OSReport(const char* format, ...) {
    char buffer[1024];
    va_list args;
    va_start(args, format);
    std::vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    state().config.hal->log(buffer);
}

uint64_t OSGetTime() {
    auto& s = state();
    uint64_t elapsed_ns = s.config.hal->nowNs() - s.boot_ns;
    // ticks = ns * 40.5e6 / 1e9, computed without overflow for long uptimes
    return elapsed_ns / 1000 * kTicksPerSecond / 1000000 +
           elapsed_ns % 1000 * kTicksPerSecond / 1000000000;
}

uint32_t OSGetTick() { return static_cast<uint32_t>(OSGetTime()); }

void* OSGetArenaLo() { return state().arena_lo; }
void* OSGetArenaHi() { return state().arena_hi; }

void OSSetArenaLo(void* lo) {
    state().arena_lo = static_cast<uint8_t*>(lo);
}

void OSSetArenaHi(void* hi) {
    state().arena_hi = static_cast<uint8_t*>(hi);
}

void* OSAllocFromArenaLo(size_t size, size_t alignment) {
    auto& s = state();
    auto addr = reinterpret_cast<uintptr_t>(s.arena_lo);
    addr = (addr + alignment - 1) & ~(alignment - 1);
    uint8_t* result = reinterpret_cast<uint8_t*>(addr);
    if (result + size > s.arena_hi) {
        OSReport("OSAllocFromArenaLo: out of arena (%zu bytes requested)", size);
        return nullptr;
    }
    s.arena_lo = result + size;
    return result;
}

}  // namespace gcrt
