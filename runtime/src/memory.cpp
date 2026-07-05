#include "gcrt/memory.h"

#include <cstring>
#include <stdexcept>

namespace gcrt {
namespace {

// Host-independent big-endian pack/unpack.
uint16_t loadBE16(const uint8_t* p) { return (p[0] << 8) | p[1]; }
uint32_t loadBE32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) |
           (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) << 8) | p[3];
}
void storeBE16(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v >> 8);
    p[1] = static_cast<uint8_t>(v);
}
void storeBE32(uint8_t* p, uint32_t v) {
    p[0] = static_cast<uint8_t>(v >> 24);
    p[1] = static_cast<uint8_t>(v >> 16);
    p[2] = static_cast<uint8_t>(v >> 8);
    p[3] = static_cast<uint8_t>(v);
}

}  // namespace

Memory::Memory() : ram_(kMem1Bytes, 0) {}

bool Memory::resolve(uint32_t guest_addr, size_t size, size_t* offset) const {
    uint32_t base;
    if (guest_addr >= kMem1Base && guest_addr < kMem1Base + kMem1Bytes) {
        base = kMem1Base;
    } else if (guest_addr >= kMem1UncachedBase &&
               guest_addr < kMem1UncachedBase + kMem1Bytes) {
        base = kMem1UncachedBase;
    } else {
        return false;
    }
    uint32_t region_offset = guest_addr - base;
    // guard against a range that starts in-region but runs past its end
    if (size > kMem1Bytes || region_offset > kMem1Bytes - size) return false;
    *offset = region_offset;
    return true;
}

bool Memory::isMapped(uint32_t guest_addr, size_t size) const {
    size_t offset;
    return resolve(guest_addr, size, &offset);
}

uint8_t* Memory::translate(uint32_t guest_addr, size_t size) {
    size_t offset;
    if (!resolve(guest_addr, size, &offset)) {
        throw std::out_of_range("gcrt: unmapped guest address");
    }
    return ram_.data() + offset;
}

const uint8_t* Memory::translate(uint32_t guest_addr, size_t size) const {
    size_t offset;
    if (!resolve(guest_addr, size, &offset)) {
        throw std::out_of_range("gcrt: unmapped guest address");
    }
    return ram_.data() + offset;
}

uint8_t Memory::read_u8(uint32_t addr) const { return *translate(addr, 1); }
uint16_t Memory::read_u16(uint32_t addr) const {
    return loadBE16(translate(addr, 2));
}
uint32_t Memory::read_u32(uint32_t addr) const {
    return loadBE32(translate(addr, 4));
}
float Memory::read_f32(uint32_t addr) const {
    uint32_t bits = read_u32(addr);
    float f;
    std::memcpy(&f, &bits, sizeof(f));
    return f;
}

void Memory::write_u8(uint32_t addr, uint8_t value) {
    *translate(addr, 1) = value;
}
void Memory::write_u16(uint32_t addr, uint16_t value) {
    storeBE16(translate(addr, 2), value);
}
void Memory::write_u32(uint32_t addr, uint32_t value) {
    storeBE32(translate(addr, 4), value);
}
void Memory::write_f32(uint32_t addr, float value) {
    uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    write_u32(addr, bits);
}

void Memory::readBlock(uint32_t addr, void* dst, size_t size) const {
    std::memcpy(dst, translate(addr, size), size);
}
void Memory::writeBlock(uint32_t addr, const void* src, size_t size) {
    std::memcpy(translate(addr, size), src, size);
}
void Memory::zero(uint32_t addr, size_t size) {
    std::memset(translate(addr, size), 0, size);
}

}  // namespace gcrt
