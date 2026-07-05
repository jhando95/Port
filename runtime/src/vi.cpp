#include "gcrt/vi.h"

#include "gcrt/os.h"

namespace gcrt {
namespace {

constexpr double kNtscHz = 59.94;

double g_frame_hz = kNtscHz;
uint32_t g_retrace_count = 0;
uint64_t g_next_retrace_ns = 0;
VIRetraceCallback g_post_retrace = nullptr;

}  // namespace

void VIInit() {
    g_retrace_count = 0;
    g_post_retrace = nullptr;
    g_next_retrace_ns = OSHal().nowNs();
}

void VISetFrameRateForTesting(double hz) { g_frame_hz = hz; }

void VIWaitForRetrace() {
    if (g_frame_hz > 0) {
        uint64_t period_ns = static_cast<uint64_t>(1e9 / g_frame_hz);
        uint64_t now = OSHal().nowNs();
        if (g_next_retrace_ns > now) {
            OSHal().sleepNs(g_next_retrace_ns - now);
        }
        uint64_t base = g_next_retrace_ns > now ? g_next_retrace_ns : now;
        g_next_retrace_ns = base + period_ns;
    }
    ++g_retrace_count;
    if (g_post_retrace) g_post_retrace(g_retrace_count);
}

uint32_t VIGetRetraceCount() { return g_retrace_count; }

VIRetraceCallback VISetPostRetraceCallback(VIRetraceCallback callback) {
    VIRetraceCallback previous = g_post_retrace;
    g_post_retrace = callback;
    return previous;
}

}  // namespace gcrt
