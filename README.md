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
gcport dol info extracted/sys/main.dol
gcport yaz0 decompress file.szs file.arc
```

## Quick start (runtime)

```sh
cmake -S runtime -B runtime/build
cmake --build runtime/build
ctest --test-dir runtime/build --output-on-failure
```

## Status

Milestone 1: format tooling + runtime skeleton. Nothing runs a game yet — the
next milestones (recompiled code integration, GX graphics translation) require a
user-supplied disc dump to develop against.
