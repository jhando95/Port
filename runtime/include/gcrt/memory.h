// Emulated GameCube address space.
//
// A statically-recompiled game keeps referencing the original absolute
// addresses baked into its binary (globals at 0x8xxxxxxx, etc.), so the
// runtime provides a flat backing store those addresses resolve into.
//
// GameCube memory map (what we model):
//   MEM1  0x80000000..0x81800000  24 MiB, cached
//         0xC0000000..0xC1800000  same RAM, uncached mirror
// Guest data is big-endian; the typed accessors byte-swap on
// little-endian hosts so recompiled code sees correct values regardless of
// host endianness.
#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace gcrt {

constexpr uint32_t kMem1Base = 0x80000000u;
constexpr uint32_t kMem1UncachedBase = 0xC0000000u;
constexpr uint32_t kMem1Bytes = 24u * 1024 * 1024;

class Memory {
public:
    Memory();

    // Translate a guest address to a host pointer for `size` bytes. Throws
    // std::out_of_range if the range is unmapped or would overrun a region.
    uint8_t* translate(uint32_t guest_addr, size_t size = 1);
    const uint8_t* translate(uint32_t guest_addr, size_t size = 1) const;

    bool isMapped(uint32_t guest_addr, size_t size = 1) const;

    // Big-endian typed accessors (guest byte order).
    uint8_t read_u8(uint32_t addr) const;
    uint16_t read_u16(uint32_t addr) const;
    uint32_t read_u32(uint32_t addr) const;
    float read_f32(uint32_t addr) const;

    void write_u8(uint32_t addr, uint8_t value);
    void write_u16(uint32_t addr, uint16_t value);
    void write_u32(uint32_t addr, uint32_t value);
    void write_f32(uint32_t addr, float value);

    // Bulk copy in/out of guest memory.
    void readBlock(uint32_t addr, void* dst, size_t size) const;
    void writeBlock(uint32_t addr, const void* src, size_t size);
    void zero(uint32_t addr, size_t size);

private:
    // Resolve a guest address to an offset within `ram_`, normalizing the
    // cached and uncached MEM1 windows to the same storage.
    bool resolve(uint32_t guest_addr, size_t size, size_t* offset) const;

    std::vector<uint8_t> ram_;  // MEM1 backing store
};

}  // namespace gcrt
