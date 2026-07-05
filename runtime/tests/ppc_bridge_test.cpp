// Integration test: run recompiled PowerPC code (generated from the Python
// tool at build time) against a live gcrt::Memory through the runtime bridge.
// This is the seam between the two halves of the project — the recompiler's
// output and the C++ runtime — exercised end to end.
#include <cstdio>

#include "gcrt/memory.h"
#include "gcrt/ppc.h"

// Defined in the build-time generated translation unit (make_recomp.py).
extern "C" void recomp_program(PpcContext* ctx);

using namespace gcrt;

int main() {
    int failures = 0;
    auto check = [&](bool cond, const char* what) {
        if (!cond) {
            std::fprintf(stderr, "FAIL: %s\n", what);
            ++failures;
        }
    };

    Memory mem;
    PpcBindMemory(&mem);
    PpcResetUnimplementedCount();

    PpcContext ctx;
    for (int i = 0; i < 32; ++i) {
        ctx.gpr[i] = 0;
        ctx.fpr[i] = 0.0;
    }
    ctx.lr = ctx.ctr = ctx.cr = ctx.xer = 0;

    recomp_program(&ctx);

    // The program stored 42 at 0x80003000 and computed r5 = 42 + 42.
    check(ctx.gpr[3] == 0x80003000, "r3 address computed via lis/ori");
    check(ctx.gpr[5] == 84, "r5 == 84 from store/load/add");
    check(mem.read_u32(0x80003000) == 42,
          "guest memory holds the stored value");
    check(PpcUnimplementedCount() == 0, "no unimplemented instructions hit");

    // ppc_call dispatch: register the program at an address and call it.
    PpcClearFunctions();
    PpcRegisterFunction(0x80003100, recomp_program);
    PpcContext ctx2;
    for (int i = 0; i < 32; ++i) {
        ctx2.gpr[i] = 0;
        ctx2.fpr[i] = 0.0;
    }
    ctx2.lr = ctx2.ctr = ctx2.cr = ctx2.xer = 0;
    ppc_call(&ctx2, 0x80003100);
    check(ctx2.gpr[5] == 84, "dispatched call ran the function");

    // An unregistered call target routes to the unimplemented handler.
    PpcResetUnimplementedCount();
    ppc_call(&ctx2, 0xDEAD0000);
    check(PpcUnimplementedCount() == 1, "unknown call target counted");

    PpcBindMemory(nullptr);
    if (failures == 0) {
        std::printf("gcrt ppc bridge test: all checks passed\n");
        return 0;
    }
    std::fprintf(stderr, "gcrt ppc bridge test: %d failure(s)\n", failures);
    return 1;
}
