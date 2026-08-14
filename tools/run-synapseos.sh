#!/usr/bin/env bash
# Run Synapse Core from the checkout against the current desktop session.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/archiso/airootfs/usr/bin:$PATH"
export SYNAPSEOS_LIB="$ROOT/archiso/airootfs/usr/lib/synapseos"

cmd="${1:-core}"
shift || true

case "$cmd" in
    core)     exec synapseos-core "$@" ;;
    overlay)  exec synapseos-overlay "$@" ;;
    mcp)      exec synapseos-mcp "$@" ;;
    ctl)      exec synapsectl "$@" ;;
    test)     exec python3 -m unittest discover -s "$ROOT/tests" -v ;;
    *)
        echo "usage: $0 {core|overlay|mcp|ctl|test} [args…]" >&2
        exit 2
        ;;
esac
