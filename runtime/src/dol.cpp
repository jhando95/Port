#include "gcrt/dol.h"

#include <stdexcept>

namespace gcrt {
namespace {

constexpr int kNumText = 7;
constexpr int kNumData = 11;
constexpr int kNumSections = kNumText + kNumData;
constexpr size_t kHeaderSize = 0x100;

uint32_t be32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) |
           (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}

}  // namespace

DolInfo LoadDol(Memory& mem, const uint8_t* data, size_t size) {
    if (size < kHeaderSize) {
        throw std::invalid_argument("gcrt: DOL smaller than header");
    }

    uint32_t offsets[kNumSections];
    uint32_t addrs[kNumSections];
    uint32_t sizes[kNumSections];
    for (int i = 0; i < kNumSections; ++i) {
        offsets[i] = be32(data + i * 4);
        addrs[i] = be32(data + 0x48 + i * 4);
        sizes[i] = be32(data + 0x90 + i * 4);
    }
    uint32_t bss_address = be32(data + 0xD8);
    uint32_t bss_size = be32(data + 0xDC);
    uint32_t entry_point = be32(data + 0xE0);

    DolInfo info;
    info.entry_point = entry_point;
    info.bss_address = bss_address;
    info.bss_size = bss_size;

    for (int i = 0; i < kNumSections; ++i) {
        uint32_t off = offsets[i], addr = addrs[i], sz = sizes[i];
        if (off == 0 && addr == 0 && sz == 0) continue;  // unused slot
        if (off + sz > size) {
            throw std::invalid_argument("gcrt: DOL section overruns file");
        }
        if (!mem.isMapped(addr, sz)) {
            throw std::invalid_argument(
                "gcrt: DOL section load address is unmapped");
        }
        mem.writeBlock(addr, data + off, sz);
        if (i < kNumText) {
            ++info.text_sections;
        } else {
            ++info.data_sections;
        }
    }

    // Zero the BSS where it falls in mapped RAM. Some titles declare a BSS
    // that nominally spans past MEM1; clamp to the largest mapped span via
    // binary search rather than the full requested size.
    if (bss_size > 0 && mem.isMapped(bss_address, 1)) {
        uint32_t lo = 1, hi = bss_size, clamped = 1;
        while (lo <= hi) {
            uint32_t mid = lo + (hi - lo) / 2;
            if (mem.isMapped(bss_address, mid)) {
                clamped = mid;
                lo = mid + 1;
            } else {
                if (mid == 0) break;
                hi = mid - 1;
            }
        }
        mem.zero(bss_address, clamped);
    }

    return info;
}

}  // namespace gcrt
