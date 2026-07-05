#!/usr/bin/env python3
"""Build a small valid DOL with the gcport tool, for the runtime loader test.

Writes to the path given as argv[1]. Uses realistic GameCube load addresses so
the runtime's memory model has to place the sections correctly.
"""

import sys
from pathlib import Path

# Import gcport from the repo's tools/ directory without installation.
TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

from gcport import dol  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: make_dol.py <output.dol>", file=sys.stderr)
        return 1

    text = b"\x60\x00\x00\x00\x4E\x80\x00\x20"  # ppc nop; blr
    data = b"gcport->gcrt\x00\x00\x00\x00"
    sections = [
        dol.DolSection("text", 0, 0x100, 0x80003100, len(text)),
        dol.DolSection("data", 0, 0x100 + len(text), 0x80100000, len(data)),
    ]
    image = dol.build(
        sections,
        bss_address=0x80200000,
        bss_size=0x4000,
        entry_point=0x80003100,
        payloads={".text0": text, ".data0": data},
    )
    Path(sys.argv[1]).write_bytes(image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
