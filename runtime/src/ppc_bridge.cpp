// Implements the recompiler runtime contract (ppc_runtime.h) over a live
// gcrt::Memory and a guest-address -> recompiled-function dispatch table.
#include "gcrt/ppc.h"

#include <cstdio>
#include <cstring>
#include <unordered_map>

namespace {

gcrt::Memory* g_memory = nullptr;
std::unordered_map<uint32_t, gcrt::PpcFunction> g_functions;
uint32_t g_unimplemented = 0;

gcrt::Memory& mem() {
    // Recompiled code should never run before PpcBindMemory; guard anyway.
    return *g_memory;
}

}  // namespace

namespace gcrt {

void PpcBindMemory(Memory* memory) { g_memory = memory; }
void PpcRegisterFunction(uint32_t address, PpcFunction fn) {
    g_functions[address] = fn;
}
void PpcClearFunctions() { g_functions.clear(); }
uint32_t PpcUnimplementedCount() { return g_unimplemented; }
void PpcResetUnimplementedCount() { g_unimplemented = 0; }

}  // namespace gcrt

extern "C" {

uint8_t ppc_read_u8(PpcContext*, uint32_t ea) { return mem().read_u8(ea); }
uint16_t ppc_read_u16(PpcContext*, uint32_t ea) { return mem().read_u16(ea); }
uint32_t ppc_read_u32(PpcContext*, uint32_t ea) { return mem().read_u32(ea); }
void ppc_write_u8(PpcContext*, uint32_t ea, uint8_t v) { mem().write_u8(ea, v); }
void ppc_write_u16(PpcContext*, uint32_t ea, uint16_t v) { mem().write_u16(ea, v); }
void ppc_write_u32(PpcContext*, uint32_t ea, uint32_t v) { mem().write_u32(ea, v); }

float ppc_read_float(PpcContext*, uint32_t ea) { return mem().read_f32(ea); }
void ppc_write_float(PpcContext*, uint32_t ea, float v) { mem().write_f32(ea, v); }

double ppc_read_double(PpcContext*, uint32_t ea) {
    uint64_t hi = mem().read_u32(ea);
    uint64_t lo = mem().read_u32(ea + 4);
    uint64_t bits = (hi << 32) | lo;
    double d;
    std::memcpy(&d, &bits, sizeof(d));
    return d;
}
void ppc_write_double(PpcContext*, uint32_t ea, double v) {
    uint64_t bits;
    std::memcpy(&bits, &v, sizeof(bits));
    mem().write_u32(ea, static_cast<uint32_t>(bits >> 32));
    mem().write_u32(ea + 4, static_cast<uint32_t>(bits));
}

void ppc_call(PpcContext* ctx, uint32_t target) {
    auto it = g_functions.find(target);
    if (it != g_functions.end()) {
        it->second(ctx);
    } else {
        ppc_unimplemented(ctx, target, 0);
    }
}

void ppc_unimplemented(PpcContext*, uint32_t address, uint32_t raw) {
    ++g_unimplemented;
    std::fprintf(stderr,
                 "gcrt: unimplemented at %08x (raw %08x)\n", address, raw);
}

// C-linkage entry point recompiled translation units call from their generated
// ppc_register_all() to populate the dispatch table.
void ppc_register_function(uint32_t address, PpcFunctionPtr fn) {
    gcrt::PpcRegisterFunction(address, fn);  // identical signatures
}

}  // extern "C"
