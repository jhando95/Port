#!/usr/bin/env python3
"""Recompile a small memory-using PowerPC program to C for the bridge test.

Emits a single translation unit (argv[1]) that #includes the runtime contract
and defines `recomp_program`. The program computes into guest memory so the
test can observe the effect through a real gcrt::Memory:

    lis  r3, 0x8000        ; r3 = 0x80003000 (a MEM1 address)
    ori  r3, r3, 0x3000
    li   r4, 42
    stw  r4, 0(r3)         ; guest memory write
    lwz  r5, 0(r3)         ; read it back
    add  r5, r5, r4        ; r5 = 84
    blr
"""

import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

from gcport.ppc import recompile_function  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: make_recomp.py <output.c>", file=sys.stderr)
        return 1
    words = [
        0x3C608000,  # lis  r3, 0x8000
        0x60633000,  # ori  r3, r3, 0x3000
        0x3880002A,  # li   r4, 42
        0x90830000,  # stw  r4, 0(r3)
        0x80A30000,  # lwz  r5, 0(r3)
        0x7CA52214,  # add  r5, r5, r4
        0x4E800020,  # blr
    ]
    code = b"".join(struct.pack(">I", w) for w in words)
    func = recompile_function(code, 0x80003100, "recomp_program")
    out = f'#include "gcrt/ppc_runtime.h"\n\n{func}\n'
    Path(sys.argv[1]).write_text(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
