// C++ binding API for the recompiler runtime bridge.
//
// The recompiled game code (generated C) calls the ppc_* hooks declared in
// ppc_runtime.h. This header lets the host bind those hooks to a live
// gcrt::Memory and register recompiled functions so ppc_call() can dispatch
// between them. `ppc_runtime.h` is the generated contract; keep the two in
// sync (a test guards against drift).
#pragma once

#include <cstdint>

#include "gcrt/memory.h"
#include "gcrt/ppc_runtime.h"

namespace gcrt {

using PpcFunction = void (*)(PpcContext*);

// Bind the memory the ppc_read_*/ppc_write_* hooks operate on. Must be called
// before running recompiled code. Passing nullptr unbinds.
void PpcBindMemory(Memory* memory);

// Register a recompiled function at its guest entry address so ppc_call() can
// reach it. Unregistered targets route to the unimplemented handler.
void PpcRegisterFunction(uint32_t address, PpcFunction fn);
void PpcClearFunctions();

// Number of times ppc_unimplemented has fired since the last reset — lets
// tests assert a routine ran with no unsupported instructions.
uint32_t PpcUnimplementedCount();
void PpcResetUnimplementedCount();

}  // namespace gcrt
