"""PowerPC (Gekko / PPC750) decoding and static recompilation to C.

The GameCube CPU is a PowerPC 750CXe ("Gekko"). A static-recompilation port
translates the game's machine code into C ahead of time; this package is that
translator's front half (decode) and a first cut of its back half (C emission)
for the common integer, load/store, compare, and branch instructions.

Scope is deliberately a subset — enough to demonstrate a correct, testable
pipeline and to grow instruction-by-instruction. Floating point, paired
singles (Gekko's SIMD), and the supervisor instructions are not handled yet;
unknown instructions emit an explicit trap rather than wrong code.
"""

from .decode import Instruction, decode, disassemble  # noqa: F401
from .recompile import (  # noqa: F401
    RUNTIME_HEADER,
    discover_functions,
    recompile_function,
    recompile_program,
)
