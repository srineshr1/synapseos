"""python -m synapseos {core,overlay,mcp,ctl}"""

from __future__ import annotations

import sys


def main() -> int:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "core"
    rest = argv[1:]
    if cmd in {"core", "daemon"}:
        from .server import main as run
        return run(rest)
    if cmd == "overlay":
        from .overlay import main as run
        return run(rest)
    if cmd == "mcp":
        from .server import main as run
        return run(["--stdio", *rest])
    if cmd in {"ctl", "synapsectl"}:
        from .ctl import main as run
        return run(rest)
    print("usage: python -m synapseos {core|overlay|mcp|ctl} [args…]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
