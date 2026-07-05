// VI service: video timing. Games structure their main loop around
// VIWaitForRetrace(); we pace it to NTSC 59.94 Hz through the HAL clock.
#pragma once

#include <cstdint>

namespace gcrt {

using VIRetraceCallback = void (*)(uint32_t retrace_count);

void VIInit();
void VIWaitForRetrace();
uint32_t VIGetRetraceCount();
VIRetraceCallback VISetPostRetraceCallback(VIRetraceCallback callback);

// Test/tooling hook: 0 disables real-time pacing (retraces are instant).
void VISetFrameRateForTesting(double hz);

}  // namespace gcrt
