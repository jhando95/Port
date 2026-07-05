// DOL executable loader: parses a GameCube DOL image and places its sections
// into emulated guest memory at their load addresses, then zeroes BSS. This
// is the boot step a recompiled port performs before transferring control to
// the (recompiled) entry point.
//
// See tools/gcport/dol.py for the authoritative format description; this is
// the run-time counterpart.
#pragma once

#include <cstdint>

#include "gcrt/memory.h"

namespace gcrt {

struct DolInfo {
    uint32_t entry_point = 0;
    uint32_t bss_address = 0;
    uint32_t bss_size = 0;
    int text_sections = 0;
    int data_sections = 0;
};

// Loads a DOL image (size bytes) into `mem`. Returns the parsed metadata.
// Throws std::invalid_argument on a malformed header or a section whose load
// address is unmapped. BSS is zeroed only where it lands in mapped RAM.
DolInfo LoadDol(Memory& mem, const uint8_t* data, size_t size);

}  // namespace gcrt
