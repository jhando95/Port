#!/usr/bin/env python3
"""Fail if the committed ppc_runtime.h has drifted from the recompiler's
RUNTIME_HEADER. Regenerate with:

    python3 -c "import sys; sys.path.insert(0,'tools'); \\
        from gcport.ppc import RUNTIME_HEADER; \\
        open('runtime/include/gcrt/ppc_runtime.h','w').write(RUNTIME_HEADER)"
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

from gcport.ppc import RUNTIME_HEADER  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_header.py <ppc_runtime.h>", file=sys.stderr)
        return 1
    committed = Path(sys.argv[1]).read_text()
    if committed != RUNTIME_HEADER:
        print("ppc_runtime.h is out of sync with the recompiler's "
              "RUNTIME_HEADER — regenerate it (see this file's docstring).",
              file=sys.stderr)
        return 1
    print("ppc_runtime.h matches the recompiler contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
