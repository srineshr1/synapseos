#!/usr/bin/env bash
# Wrapper: multipart-upload ISOs via the Worker admin API.
# Requires .iso-upload-secret (or ISO_UPLOAD_SECRET in the environment).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${ISO_UPLOAD_SECRET:-}" && -f .iso-upload-secret ]]; then
  ISO_UPLOAD_SECRET="$(cat .iso-upload-secret)"
  export ISO_UPLOAD_SECRET
fi

if [[ -z "${ISO_UPLOAD_SECRET:-}" ]]; then
  echo "Missing ISO_UPLOAD_SECRET (or .iso-upload-secret file)." >&2
  echo "Create it with: printf '%s' \"\$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')\" | npx wrangler secret put ISO_UPLOAD_SECRET" >&2
  exit 1
fi

exec node tools/upload-isos-r2.mjs "$@"
