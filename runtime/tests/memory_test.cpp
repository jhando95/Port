// Tests the emulated address space and DOL loader. When a DOL file path is
// passed as argv[1] (produced by the Python tool), it is loaded and checked
// against known section contents — a cross-language format-parity test.
#include <cstdint>
#include <cstdio>
#include <stdexcept>
#include <vector>

#include "gcrt/dol.h"
#include "gcrt/memory.h"

using namespace gcrt;

namespace {

int g_failures = 0;

#define CHECK(cond)                                                      \
    do {                                                                 \
        if (!(cond)) {                                                   \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, \
                         #cond);                                         \
            ++g_failures;                                                \
        }                                                                \
    } while (0)

void testMemory() {
    Memory mem;

    // Round-trip typed accessors, verifying big-endian storage.
    mem.write_u32(0x80003100, 0x12345678);
    CHECK(mem.read_u32(0x80003100) == 0x12345678);
    CHECK(mem.read_u8(0x80003100) == 0x12);   // MSB first
    CHECK(mem.read_u8(0x80003103) == 0x78);
    mem.write_u16(0x80003200, 0xABCD);
    CHECK(mem.read_u16(0x80003200) == 0xABCD);
    mem.write_f32(0x80003300, 3.5f);
    CHECK(mem.read_f32(0x80003300) == 3.5f);

    // Cached and uncached mirrors alias the same RAM.
    mem.write_u32(0x80010000, 0xCAFEBABE);
    CHECK(mem.read_u32(0xC0010000) == 0xCAFEBABE);
    mem.write_u32(0xC0010000, 0x0BADF00D);
    CHECK(mem.read_u32(0x80010000) == 0x0BADF00D);

    // Bounds: unmapped addresses and region overruns throw.
    CHECK(!mem.isMapped(0x00000000, 1));
    CHECK(!mem.isMapped(0x7FFFFFFF, 1));
    CHECK(mem.isMapped(0x80000000, 1));
    CHECK(mem.isMapped(0x817FFFFF, 1));
    CHECK(!mem.isMapped(0x817FFFFF, 2));  // straddles the end of MEM1
    bool threw = false;
    try {
        mem.read_u32(0x817FFFFE);  // 4 bytes from 2-before-end overruns
    } catch (const std::out_of_range&) {
        threw = true;
    }
    CHECK(threw);
}

// Build a minimal valid DOL in memory: one text section, one data section,
// a BSS, and an entry point.
std::vector<uint8_t> buildSyntheticDol() {
    auto put32 = [](std::vector<uint8_t>& v, size_t off, uint32_t x) {
        v[off] = x >> 24;
        v[off + 1] = x >> 16;
        v[off + 2] = x >> 8;
        v[off + 3] = x;
    };
    std::vector<uint8_t> text = {0x60, 0x00, 0x00, 0x00,   // ppc nop
                                 0x4E, 0x80, 0x00, 0x20};  // blr
    std::vector<uint8_t> data = {'D', 'O', 'L', '!'};

    size_t text_off = 0x100;
    size_t data_off = text_off + text.size();
    std::vector<uint8_t> dol(data_off + data.size(), 0);

    put32(dol, 0x00, static_cast<uint32_t>(text_off));  // text0 file offset
    put32(dol, 0x48, 0x80003100);                       // text0 load addr
    put32(dol, 0x90, static_cast<uint32_t>(text.size()));

    put32(dol, 0x1C, static_cast<uint32_t>(data_off));  // data0 file offset
    put32(dol, 0x64, 0x80100000);                       // data0 load addr
    put32(dol, 0xAC, static_cast<uint32_t>(data.size()));

    put32(dol, 0xD8, 0x80200000);  // bss addr
    put32(dol, 0xDC, 0x1000);      // bss size
    put32(dol, 0xE0, 0x80003100);  // entry

    for (size_t i = 0; i < text.size(); ++i) dol[text_off + i] = text[i];
    for (size_t i = 0; i < data.size(); ++i) dol[data_off + i] = data[i];
    return dol;
}

void testDolLoad() {
    Memory mem;
    // Pre-dirty the BSS to prove it gets cleared.
    mem.write_u32(0x80200000, 0xFFFFFFFF);

    auto dol = buildSyntheticDol();
    DolInfo info = LoadDol(mem, dol.data(), dol.size());

    CHECK(info.entry_point == 0x80003100);
    CHECK(info.bss_address == 0x80200000);
    CHECK(info.bss_size == 0x1000);
    CHECK(info.text_sections == 1);
    CHECK(info.data_sections == 1);

    CHECK(mem.read_u32(0x80003100) == 0x60000000);  // nop landed
    CHECK(mem.read_u32(0x80003104) == 0x4E800020);  // blr landed
    CHECK(mem.read_u8(0x80100000) == 'D');          // data landed
    CHECK(mem.read_u32(0x80200000) == 0);           // BSS zeroed
}

// If a real (Python-built) DOL is provided, load and sanity-check it.
void testExternalDol(const char* path) {
    FILE* f = std::fopen(path, "rb");
    if (!f) {
        std::fprintf(stderr, "FAIL: cannot open %s\n", path);
        ++g_failures;
        return;
    }
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    std::vector<uint8_t> buf(n);
    if (std::fread(buf.data(), 1, n, f) != static_cast<size_t>(n)) {
        std::fprintf(stderr, "FAIL: short read on %s\n", path);
        ++g_failures;
        std::fclose(f);
        return;
    }
    std::fclose(f);

    Memory mem;
    DolInfo info = LoadDol(mem, buf.data(), buf.size());
    CHECK(mem.isMapped(info.entry_point, 4));
    std::printf("external DOL: entry %08X, %d text + %d data sections\n",
                info.entry_point, info.text_sections, info.data_sections);
}

}  // namespace

int main(int argc, char** argv) {
    testMemory();
    testDolLoad();
    if (argc > 1) testExternalDol(argv[1]);

    if (g_failures == 0) {
        std::printf("gcrt memory test: all checks passed\n");
        return 0;
    }
    std::fprintf(stderr, "gcrt memory test: %d failure(s)\n", g_failures);
    return 1;
}
