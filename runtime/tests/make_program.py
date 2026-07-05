#!/usr/bin/env python3
"""Recompile a multi-function PowerPC program to a C translation unit.

Emits (to argv[1]) a program where one function calls another, exercising
function discovery + the runtime dispatch table:

    0x80003100 main:  li r3, 0
                      bl  add        ; dispatched call to 0x80003110
                      addi r3, r3, 1 ; after return: r3 = 42 + 1 = 43
                      blr
    0x80003110 add:   li r3, 42
                      blr
"""

import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

from gcport.ppc import recompile_program  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: make_program.py <output.c>", file=sys.stderr)
        return 1
    words = [
        0x38600000,  # 0x00 li   r3, 0
        0x4800000D,  # 0x04 bl   +12  -> 0x80003110
        0x38630001,  # 0x08 addi r3, r3, 1
        0x4E800020,  # 0x0c blr
        0x3860002A,  # 0x10 li   r3, 42
        0x4E800020,  # 0x14 blr
    ]
    code = b"".join(struct.pack(">I", w) for w in words)
    Path(sys.argv[1]).write_text(recompile_program(code, 0x80003100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
