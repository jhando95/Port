# Port

Building a **native PC port pipeline** for GameCube games — primary target:
**Mario Kart: Double Dash!!**, with Super Smash Bros. Melee as the second target.
Everything here is game-agnostic where possible.

**This repository contains no game code or assets and never will.** You must dump
your own disc from a console you own. See [ROADMAP.md](ROADMAP.md) for the legal
ground rules and the overall strategy.

## How a native build gets made

A native port is assembled from three parts:

| Part | Where it comes from |
|------|---------------------|
| Game logic (CPU code) | Static recompilation of *your* dump's `main.dol` (DolRecomp-style), or a finished decompilation |
| Game assets | Extracted from *your* dump at build/run time |
| Platform layer | **`runtime/` in this repo** — original code replacing the GameCube OS, disc, input, and video interfaces with PC equivalents |

The tooling that glues it together lives in `tools/`.

## Repository layout

- **`tools/`** — `gcport`, a Python package + CLI for GameCube formats:
  - GCM/ISO disc images: inspect, extract, rebuild (the rebuild step is how
    modified assets — "DLC" — get back into a playable image)
  - RARC archives (`.arc`/`.szs`, where MKDD stores tracks and characters):
    list, extract, create, with transparent Yaz0 handling
  - BTI textures: decode any common GX pixel format (I4/I8/IA4/IA8/RGB565/
    RGB5A3/RGBA32/CMPR) to PNG, and encode PNG back to BTI — custom texture
    mods without external image libraries
  - DOL executables: parse headers, sections, entry point
  - Yaz0 compression: decompress and compress
- **`runtime/`** — `gcrt`, a C++ runtime library skeleton implementing GameCube
  system services on PC (OS time/arena, DVD reads mapped to an extracted asset
  directory, controller input, video timing) behind a swappable HAL.
- **`docs/`** — [architecture and pipeline docs](docs/ARCHITECTURE.md).

## Quick start (tools)

```sh
cd tools
pip install -e ".[dev]"
pytest                        # run the test suite

gcport iso info game.iso      # show disc header, DOL, FST stats
gcport iso extract game.iso -o extracted/
gcport iso build extracted/ -o rebuilt.iso

gcport verify extracted/      # parse every archive/texture/DOL, print a report
gcport verify game.iso        # (works directly on an ISO too)
gcport dol info extracted/sys/main.dol
gcport yaz0 decompress file.szs file.arc

gcport ppc disasm extracted/sys/main.dol --offset 0x100 --count 40   # PowerPC

gcport rarc list extracted/files/Course/Luigi.arc
gcport rarc extract extracted/files/Course/Luigi.arc -o luigi/
gcport rarc create luigi/ -o Luigi.arc        # add --yaz0 for .szs

gcport bti decode luigi/textures/road.bti road.png
gcport bti encode road_edited.png road.bti --format RGB5A3  # CMPR is decode-only
```

## Quick start (runtime)

```sh
cmake -S runtime -B runtime/build
cmake --build runtime/build
ctest --test-dir runtime/build --output-on-failure
```

With SDL2 development headers installed, the build includes `gcrt::SdlHal`
(window + keyboard/game-controller input + real frame pacing); without them
it builds headless-only with `NullHal`.

## Status

Milestone 1: format tooling + runtime skeleton. Nothing runs a game yet — the
next milestones (recompiled code integration, GX graphics translation) require a
user-supplied disc dump to develop against.
