# Architecture: GameCube → native PC pipeline

## Overview

```
your disc dump (game.iso)
        │
        ├── gcport iso extract ──────────► extracted/sys/main.dol   (game code)
        │                                  extracted/files/**       (game assets)
        │
        ├── static recompiler (DolRecomp / GCRecomp, external) ──► game logic as C/Rust
        │                                                          compiled for x86-64
        │
        └────────────────────────────┐
                                     ▼
        recompiled game logic  +  gcrt runtime (this repo)  =  native executable
                                     ▲
                     assets loaded via gcrt DVD layer from extracted/files/
```

The GameCube's CPU code calls into Nintendo's SDK libraries (Dolphin OS, DVD,
PAD, VI, GX, AX, CARD…). On console those talk to hardware. In a native port,
**gcrt** provides the same interfaces backed by PC facilities. The recompiled
game code doesn't know the difference.

### Boot sequence (what runs before the game)

1. `gcport iso extract` (offline) pulls `main.dol` and the asset tree out of
   the user's dump.
2. At startup the runtime creates the guest **Memory** (24 MiB MEM1 + uncached
   mirror), then **LoadDol** places each DOL section at its load address and
   zeroes BSS — recompiled code references these absolute addresses directly.
3. `OSInit`/`DVDInit`/`VIInit`/`GXInit`/`PADInit` bring up the subsystems.
4. Control transfers to the recompiled entry point (the recompiler emits the
   entry as a C function; the loaded data/BSS back its global state).

Steps 1–2 exist and are tested today (including a cross-language test where the
Python tool builds a DOL and the C++ loader consumes it). Step 4 is what the
static recompiler produces and is the next major integration once a dump is
available.

## gcrt subsystems

| GameCube API | gcrt implementation | Status |
|---|---|---|
| Memory (guest address space) | flat MEM1 backing store (0x80000000, 24 MiB) with the uncached mirror, big-endian typed accessors, bounds-checked translation | working |
| DOL loader (boot) | parses main.dol, places sections at their load addresses in guest memory, zeroes BSS; the step before control passes to recompiled code | working |
| OS (time, arenas, threads, reports) | `std::chrono`, malloc-backed arenas, host threads | skeleton |
| DVD (async file reads by path/entrynum) | reads from the extracted asset directory, FST-compatible path resolution | skeleton |
| PAD (controllers) | HAL input backend: SDL2 gamepad/keyboard (`SdlHal`) or headless (`NullHal`) | working |
| VI (video timing, retrace callbacks) | 59.94 Hz frame pacing, retrace callback dispatch | skeleton |
| GX (GPU command interface) | software rasterizer into an RGBA EFB: viewport/projection/modelview transforms, immediate-mode triangles, Gouraud shading, z-buffer, copy-clear, and textured triangles (all GC pixel formats, perspective-correct UVs, wrap modes, modulate-by-vertex-color). TEV stages and lighting next; a GL/Vulkan backend can replace the rasterizer behind the same API | in progress |
| AX/DSP (audio) | mixer → host audio out | not started |
| CARD (memory card) | save files on disk | not started |

The HAL (`gcrt::Hal`) isolates everything platform-facing (window, input,
audio, time) behind one interface. The `NullHal` backend lets the whole
runtime build and test headlessly in CI; an SDL backend slots in later
without touching subsystem code.

## Why static recompilation first (not decompilation)

- Double Dash's decomp is ~35% matched; Melee's ~75%. A decomp-based port needs
  ~100% (or at least all-linkable). That's years away for MKDD.
- A static recompiler translates the *entire* binary today. The port quality then
  depends on the runtime — which is exactly what we control here.
- The two paths converge: as decomps finish, recompiled modules can be swapped
  for real source module-by-module, unlocking deeper mods.

### Recompiler status (`gcport.ppc`)

A first slice of the static recompiler lives in the tooling: a PowerPC
(Gekko/PPC750) instruction **decoder** and a **C-emission back-end** covering
the common integer, logical, compare, load/store, and branch instructions. It
emits a C function per routine over a `PpcContext` register file, with
memory/branch hooks the runtime implements (backed by `gcrt::Memory`).
Correctness is proven end-to-end: a test recompiles a hand-assembled loop,
compiles the emitted C with the host compiler, runs it, and checks the result.

Scalar floating point is handled too: the FPR file (modeled as doubles),
load/store (`lfs`/`lfd`/`stfs`/`stfd`), the arithmetic and multiply-add family
(`fadd(s)`/`fsub(s)`/`fmul(s)`/`fdiv(s)`/`fmadd(s)`…, with single-precision
rounding), `fmr`/`fneg`/`fabs`/`frsp`/`fsel`, and `fcmpu`/`fcmpo`. A second
gcc-backed end-to-end test computes a real float sum through the emitted code.

FPRs are modeled as a `double`/`uint64_t` union, which gives the bit-accurate
access the integer-convert path needs: `fctiw`/`fctiwz` write the integer into
the FPR's low word and `stfiwx` stores it — the pattern behind every
float-to-int cast. Reciprocal estimates (`fres`, `frsqrte`) are emitted too,
along with the X-form **indexed** load/stores (`lwzx`/`lhzx`/`lhax`/`lbzx`/
`stwx`/`sthx`/`stbx` and the FP `lfsx`/`lfdx`/`stfsx`/`stfdx`/`stfiwx`).

Still emitted as explicit `ppc_unimplemented` traps (not wrong code): `fsqrt`
(which real Gekko traps anyway), Gekko's paired-singles (decoded for
disassembly but not emitted — their quantized load/store needs the GQR
registers), and supervisor instructions.

**Runtime bridge.** `runtime/src/ppc_bridge.cpp` implements the recompiler's
memory/branch hooks over a live `gcrt::Memory` and a guest-address→function
dispatch table (`gcrt/ppc.h`). The generated contract `ppc_runtime.h` is
committed into the runtime include tree and kept from drifting by a test that
compares it to the recompiler's `RUNTIME_HEADER`. An integration test
recompiles a memory-using program at build time, links it against the real
runtime, runs it, and checks the effect in guest memory (`r5 == 84`, and
`0x80003000` holds the stored value) — the two halves of the project proven to
connect. Function discovery (finding routine boundaries in a real `main.dol`)
and feeding the game's own code through this path are the next steps — the
first that needs a user-supplied dump.

## Where "DLC" fits

Content mods (new tracks, characters) are asset-level: unpack archive → replace/add
assets → rebuild. `gcport iso build` already closes that loop for disc images
(usable with Dolphin immediately). In the native port, the DVD layer reads loose
files, so DLC becomes literally "drop files in a directory" plus a small manifest —
no ISO rebuilding at all. Code-level mods ride on the recompiled code's function
boundaries (hook tables), same model N64Recomp ports use.

## Format notes

- **GCM/ISO**: 0x440-byte boot header (game ID, DVD magic `0xC2339F3D` at 0x1C,
  DOL/FST offsets at 0x420/0x424), bi2 at 0x440, apploader at 0x2440, then DOL,
  FST, and file data. FST is 12-byte entries (flag+name offset, offset/parent,
  length/next) + string table.
- **DOL**: 0x100-byte header; 7 text + 11 data sections (file offset, load
  address, size triplets), BSS address/size, entry point. All big-endian.
- **Yaz0**: RLE/LZ back-reference scheme, magic `Yaz0`, used to compress many
  first-party archives (`.szs`).
- **RARC/ARC** (Nintendo archive format used heavily by MKDD): implemented in
  `gcport.rarc` from community documentation, round-trip tested. Still to be
  verified against a retail archive once a user-supplied dump is available.
