# Port — Roadmap

Goal: get classic console games (starting with Mario Kart: Double Dash!!) genuinely
running on PC, with the ability to extend them — new tracks, characters, features
("DLC").

## Ground rules

- **No game assets in this repo. Ever.** No ISOs, ROMs, or files extracted from a
  disc image. Everything here is original code and tooling; anyone using it supplies
  their own dump of a game they own. This is the rule every surviving community
  project (SM64 decomp, Ship of Harkinian, OpenGOAL, Dusk) follows.
- Dump your own disc (a Wii/GameCube with CleanRip, or a compatible USB drive setup).
  Downloading ISOs is copyright infringement and also what gets projects taken down.

## The three ways a console game "runs on PC"

### 1. Emulation + mod tooling (works today)

Dolphin already runs MKDD at 4K/60fps. The modding scene around it is mature:

- [MKDD Track Patcher](https://github.com/RenolY2/mkdd-track-patcher) — patches
  custom tracks, characters, and karts into an ISO from portable ZIP mod archives.
- [MKDD Extender](https://mkdd.org/wiki/MKDD_Extender) — extends the game with up to
  144 extra race tracks and 54 battle stages: effectively a DLC framework.
- [Double Dash Deluxe](https://github.com/doubledashdeluxe/ddd) — feature/enhancement
  patches for the game.
- [Custom MKDD Wiki](https://mkdd.org/wiki/Main_Page) — file format documentation
  (BOL course files, archives, etc.) and modding tutorials.

This is where "add DLC" is achievable *now*, and where you learn the game's file
formats — knowledge that transfers directly to the harder paths below.

### 2. Decompilation → native port (the long game)

Reverse the original PowerPC binary into matching C/C++ source, then retarget it to
PC (SDL + OpenGL/Vulkan replacing the GameCube's GX graphics library). This is the
SM64 / Ship of Harkinian / OpenGOAL model, and in **May 2026 it reached GameCube**:
*Dusk*, a native PC port of Twilight Princess from the completed decomp.

- [doldecomp/mkdd](https://github.com/doldecomp/mkdd) — the Double Dash
  decompilation, currently [~35% matched](https://decomp.dev/SwareJonge/mkdd).
  Debug version only for now. Contributing here is the direct route to a real
  MKDD PC port.
- Skills/tools: PowerPC assembly, C++, Ghidra, decomp.me, objdiff,
  decomp-toolkit (dtk). See [gamecube.dev](https://gamecube.dev/) for the ecosystem.

### 3. Static recompilation (the new shortcut)

Machine-translate the PowerPC binary to C/Rust and pair it with a runtime that
implements the console's OS and graphics interfaces. N64Recomp proved the model
(Majora's Mask PC); GameCube tooling arrived recently:

- [DolRecomp](https://gbatemp.net/threads/dolrecomp-a-wii-gamecube-static-recompiler-was-recently-made-public.682687/)
  — public GameCube/Wii static recompiler emitting C.
- [GCRecomp](https://github.com/KaiserGranatapfel/GameCubeRecompiled) — experimental
  DOL→Rust recompiler.
- A [Wind Waker static recomp](https://github.com/sp00nznet/ww) exists as a
  proof of concept.

Much faster than full decompilation, but the output isn't human-readable source —
fine for *running* the game natively, harder for deep feature mods. The heavy
lifting is writing the runtime shims (GX graphics, audio, memory card, input).

## Staged plan

1. **Stage 0 — mod on Dolphin.** Dump your disc, set up Dolphin, install MKDD
   Extender + Track Patcher, play existing custom tracks. Deliverable: your own
   custom track or character mod packaged as a Patcher ZIP.
2. **Stage 1 — build tooling (this repo).** Write our own tools for MKDD file
   formats: archive pack/unpack, BOL course inspection, mod packaging. This is
   original code, safe to publish, and useful to the community.
3. **Stage 2 — go native.** Either contribute matched functions to doldecomp/mkdd,
   or experiment with DolRecomp against our own dump to get a native executable
   booting.
4. **Stage 3 — the port.** When decomp/recomp is viable: PC runtime (SDL, modern
   rendering), then real DLC-style extensibility on top — the Dusk/Harkinian model
   (those ports added 60fps, widescreen, mod loaders, etc.).

## Picking targets strategically

If the goal is "make changes and add DLC to a game running natively on PC" *soon*,
consider starting with a game whose decomp is already finished — SM64, Ocarina of
Time (Ship of Harkinian), Majora's Mask (2 Ship 2 Harkinian), Perfect Dark,
Twilight Princess (Dusk), Jak & Daxter (OpenGOAL) — and modding it, while MKDD's
decomp matures. See [PCGamingWiki's list of unofficial ports](https://www.pcgamingwiki.com/wiki/List_of_unofficial_ports).
