#!/usr/bin/env python3
"""Serve the latest SynapseOS ISO on a branded download page.

Picks the newest out/synapseos-*.iso (ignores *.prev), serves only that file
plus its checksum and the landing page, and optionally publishes it through
ngrok.

    python3 tools/serve-iso.py           # http://127.0.0.1:8765/
    python3 tools/serve-iso.py --ngrok   # same, plus a public HTTPS URL

--ngrok stops any already-running ngrok agent (free accounts allow one
tunnel). The local process that agent was forwarding is left alone.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import http.server
import json
import os
import signal
import socketserver
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
MARK = ROOT / "archiso/branding/mark.png"
CACHE = Path.home() / ".cache/synapseos-iso"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
NGROK_API = "http://127.0.0.1:4040/api/tunnels"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SynapseOS — download</title>
<link rel="icon" href="/mark.png" type="image/png">
<style>
  :root {{
    --bg: #05060a;
    --panel: #0b1018;
    --text: #e8eef7;
    --muted: #9b91b4;
    --accent: #8366F1;
    --accent-dim: #6b4fe0;
    --line: #1c1830;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; min-height: 100%; }}
  body {{
    font-family: "Segoe UI", "Noto Sans", ui-sans-serif, system-ui, sans-serif;
    color: var(--text);
    background:
      radial-gradient(900px 480px at 50% -10%, rgba(131, 102, 241, 0.22), transparent 60%),
      radial-gradient(700px 360px at 100% 100%, rgba(41, 182, 246, 0.06), transparent 55%),
      var(--bg);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 48px 20px 32px;
  }}
  main {{
    width: min(560px, 100%);
    background: color-mix(in srgb, var(--panel) 92%, black);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 36px 32px 28px;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 28px;
  }}
  .brand img {{
    width: 56px;
    height: 56px;
    border-radius: 12px;
    display: block;
  }}
  h1 {{
    margin: 0;
    font-size: 1.55rem;
    font-weight: 650;
    letter-spacing: -0.03em;
    line-height: 1.15;
  }}
  .tag {{
    margin: 4px 0 0;
    color: var(--muted);
    font-size: 0.92rem;
  }}
  .file {{
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 18px 18px 16px;
    background: #07080e;
    margin-bottom: 20px;
  }}
  .name {{
    font-weight: 600;
    font-size: 1.02rem;
    word-break: break-all;
  }}
  .meta {{
    margin-top: 6px;
    color: var(--muted);
    font-size: 0.9rem;
  }}
  .download {{
    display: block;
    text-align: center;
    text-decoration: none;
    background: var(--accent);
    color: #000;
    font-weight: 700;
    letter-spacing: -0.01em;
    padding: 13px 18px;
    border-radius: 12px;
    margin: 22px 0 10px;
  }}
  .download:hover {{ background: #947aff; }}
  .secondary {{
    display: block;
    text-align: center;
    color: var(--muted);
    font-size: 0.88rem;
    text-decoration: none;
  }}
  .secondary:hover {{ color: var(--text); }}
  .hash-label {{
    margin: 22px 0 8px;
    color: var(--muted);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .hash {{
    display: flex;
    gap: 8px;
    align-items: stretch;
  }}
  .hash code {{
    flex: 1;
    font-family: "IBM Plex Mono", "DejaVu Sans Mono", ui-monospace, monospace;
    font-size: 0.72rem;
    line-height: 1.45;
    word-break: break-all;
    background: #05060a;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px 12px;
    color: #c8c0e0;
  }}
  .hash button {{
    border: 1px solid var(--line);
    background: #16121c;
    color: var(--text);
    border-radius: 10px;
    padding: 0 12px;
    cursor: pointer;
    font: inherit;
    font-size: 0.82rem;
  }}
  .hash button:hover {{
    background: var(--accent);
    color: #000;
    border-color: var(--accent);
  }}
  h2 {{
    margin: 28px 0 10px;
    font-size: 0.78rem;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
  }}
  ol {{
    margin: 0;
    padding-left: 1.2rem;
    color: #c5cde0;
    font-size: 0.92rem;
    line-height: 1.55;
  }}
  pre {{
    margin: 12px 0 0;
    background: #05060a;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 12px 14px;
    overflow-x: auto;
    font-family: "IBM Plex Mono", "DejaVu Sans Mono", ui-monospace, monospace;
    font-size: 0.75rem;
    color: #c8c0e0;
    white-space: pre-wrap;
  }}
  footer {{
    width: min(560px, 100%);
    margin-top: 18px;
    color: var(--muted);
    font-size: 0.78rem;
    line-height: 1.45;
    text-align: center;
  }}
</style>
</head>
<body>
<main>
  <div class="brand">
    <img src="/mark.png" alt="SynapseOS">
    <div>
      <h1>SynapseOS</h1>
      <p class="tag">Arch Linux · Plasma · Catppuccin Macchiato</p>
    </div>
  </div>

  <div class="file">
    <div class="name">{name}</div>
    <div class="meta">{size} · {version}</div>
    <a class="download" href="/{name}">Download ISO</a>
    <a class="secondary" href="/{name}.sha256">SHA-256 checksum file</a>
  </div>

  <div class="hash-label">SHA-256</div>
  <div class="hash">
    <code id="hash">{sha256}</code>
    <button type="button" id="copy">Copy</button>
  </div>

  <h2>Write to a USB</h2>
  <ol>
    <li>Ventoy or balenaEtcher: copy or flash the ISO onto the stick.</li>
    <li>Or <code>dd</code> (this erases the target device):</li>
  </ol>
  <pre>sudo dd if={name} of=/dev/sdX bs=4M status=progress conv=fsync</pre>

  <h2>Download from a terminal</h2>
  <pre id="curl"></pre>
</main>
<footer>
  Private share — not a public release. The image includes proprietary AI-agent
  packages; do not redistribute it.<br>
  Made by Srinesh, Vashista, Vishnu
</footer>
<script>
  const file = {name_js};
  const curl = document.getElementById("curl");
  curl.textContent =
    'curl -L -O -H "ngrok-skip-browser-warning: 1" ' +
    location.origin + "/" + file;
  const btn = document.getElementById("copy");
  btn.addEventListener("click", async () => {{
    try {{
      await navigator.clipboard.writeText(document.getElementById("hash").textContent);
      btn.textContent = "Copied";
      setTimeout(() => btn.textContent = "Copy", 1500);
    }} catch {{
      btn.textContent = "Failed";
    }}
  }});
</script>
</body>
</html>
"""


def latest_iso() -> Path:
    images = [
        path
        for path in OUT.glob("synapseos-*.iso")
        if path.is_file() and not path.name.endswith(".prev")
    ]
    if not images:
        raise SystemExit(f"error: no synapseos-*.iso in {OUT}")
    return max(images, key=lambda p: p.stat().st_mtime)


def human_size(n: int) -> str:
    gib = n / 1024**3
    return f"{gib:.2f} GiB ({n:,} bytes)"


def iso_version(name: str) -> str:
    # synapseos-2026.08.13-x86_64.iso
    parts = name.removesuffix(".iso").split("-")
    for part in parts:
        if part[:4].isdigit() and "." in part:
            return part
    return "SynapseOS"


def checksum_cache_path(iso: Path) -> Path:
    st = iso.stat()
    return CACHE / f"{iso.name}.{st.st_size}.{int(st.st_mtime)}.sha256"


def load_or_compute_sha256(iso: Path) -> str:
    beside = iso.with_suffix(iso.suffix + ".sha256")
    cached = checksum_cache_path(iso)
    for candidate in (beside, cached):
        if candidate.is_file():
            token = candidate.read_text().split()[0].strip()
            if len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token):
                print(f"SHA-256 (cached): {token}", flush=True)
                return token.lower()

    print(f"Computing SHA-256 of {iso.name} ({human_size(iso.stat().st_size)})…", flush=True)
    digest = hashlib.sha256()
    total = iso.stat().st_size
    done = 0
    last = 0.0
    with iso.open("rb") as fh:
        while chunk := fh.read(8 * 1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            now = time.monotonic()
            if now - last >= 1.0 or done == total:
                pct = 100.0 * done / total if total else 100.0
                print(f"  {pct:5.1f}%  {done / 1024**3:.2f} / {total / 1024**3:.2f} GiB", flush=True)
                last = now
    token = digest.hexdigest()
    line = f"{token}  {iso.name}\n"
    written = False
    try:
        beside.write_text(line)
        written = True
        print(f"Wrote {beside}", flush=True)
    except OSError:
        pass
    if not written:
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_text(line)
        print(f"Wrote {cached} (out/ is not writable)", flush=True)
    print(f"SHA-256: {token}", flush=True)
    return token


def build_stage(iso: Path, sha256: str) -> Path:
    stage = Path(tempfile.mkdtemp(prefix="synapseos-iso-"))
    checksum_name = f"{iso.name}.sha256"
    checksum_src = iso.with_suffix(iso.suffix + ".sha256")
    if not checksum_src.is_file():
        checksum_src = checksum_cache_path(iso)
        if not checksum_src.is_file():
            checksum_src = stage / checksum_name
            checksum_src.write_text(f"{sha256}  {iso.name}\n")
    (stage / iso.name).symlink_to(iso.resolve())
    dest_sum = stage / checksum_name
    if checksum_src.resolve() != dest_sum:
        dest_sum.write_text(checksum_src.read_text() if checksum_src.is_file()
                            else f"{sha256}  {iso.name}\n")
    if MARK.is_file():
        (stage / "mark.png").symlink_to(MARK.resolve())
    version = iso_version(iso.name)
    page = PAGE.format(
        name=html.escape(iso.name, quote=True),
        size=html.escape(human_size(iso.stat().st_size)),
        version=html.escape(version),
        sha256=html.escape(sha256),
        name_js=json.dumps(iso.name),
    )
    (stage / "index.html").write_text(page)
    return stage


class LimitedReader:
    """File wrapper that yields at most `remaining` bytes."""

    def __init__(self, fh, remaining: int):
        self._fh = fh
        self._remaining = remaining

    def read(self, size: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if size is None or size < 0:
            size = self._remaining
        data = self._fh.read(min(size, self._remaining))
        self._remaining -= len(data)
        return data

    def close(self) -> None:
        self._fh.close()


def parse_byte_range(header: str, size: int) -> tuple[int, int] | str | None:
    """Inclusive (start, end), 'unsatisfiable', or None to ignore the header."""
    if not header.lower().startswith("bytes="):
        return None
    spec = header.split("=", 1)[1].split(",", 1)[0].strip()
    if "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        if start_s == "":
            suffix = int(end_s)
            if suffix <= 0:
                return None
            if size == 0:
                return "unsatisfiable"
            start = max(size - suffix, 0)
            end = size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start >= size or start < 0:
        return "unsatisfiable"
    end = min(end, size - 1)
    if end < start:
        return "unsatisfiable"
    return start, end


class Handler(http.server.SimpleHTTPRequestHandler):
    iso_name: str = ""

    def list_directory(self, _path):
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        return None

    def guess_type(self, path):
        if Path(path).name == self.iso_name:
            return "application/octet-stream"
        return super().guess_type(path)

    def end_headers(self):
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        if path.rstrip("/") == f"/{self.iso_name}":
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{self.iso_name}"',
            )
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        if path.endswith("/"):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            fh = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            stat = os.fstat(fh.fileno())
            size = stat.st_size
            ctype = self.guess_type(path)
            start, end = 0, max(size - 1, 0)
            status = HTTPStatus.OK
            rng = self.headers.get("Range")
            if rng:
                parsed = parse_byte_range(rng, size)
                if parsed == "unsatisfiable":
                    fh.close()
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                if isinstance(parsed, tuple):
                    start, end = parsed
                    status = HTTPStatus.PARTIAL_CONTENT
                    fh.seek(start)
            length = 0 if size == 0 else end - start + 1
            self.send_response(status)
            self.send_header("Content-type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            return LimitedReader(fh, length)
        except Exception:
            fh.close()
            raise

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def ngrok_pids() -> list[int]:
    found: list[int] = []
    proc = Path("/proc")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
        parts = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
        if not parts:
            continue
        if Path(parts[0]).name == "ngrok":
            found.append(int(entry.name))
    return found


def stop_ngrok() -> None:
    pids = ngrok_pids()
    if not pids:
        return
    for pid in pids:
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        except OSError:
            cmdline = "ngrok"
        print(f"Stopping existing ngrok pid {pid}: {cmdline.strip()}", flush=True)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    deadline = time.time() + 5
    while time.time() < deadline and ngrok_pids():
        time.sleep(0.1)
    for pid in ngrok_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def wait_public_url(timeout: float = 20.0) -> str:
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(NGROK_API, timeout=1) as resp:
                data = json.loads(resp.read().decode())
            for tunnel in data.get("tunnels", []):
                url = tunnel.get("public_url") or ""
                if url.startswith("https://"):
                    return url
                if url.startswith("http://") and not last_err:
                    last_err = url
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = str(exc)
        time.sleep(0.25)
    raise SystemExit(f"error: ngrok did not publish a URL ({last_err or 'timeout'})")


def start_ngrok(host: str, port: int) -> tuple[subprocess.Popen, str, Path]:
    stop_ngrok()
    log = Path(tempfile.gettempdir()) / "synapseos-ngrok.log"
    proc = subprocess.Popen(
        ["ngrok", "http", f"{host}:{port}", "--log=stdout", "--log-format=logfmt"],
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        url = wait_public_url()
    except SystemExit:
        if proc.poll() is not None:
            print(log.read_text()[-2000:], file=sys.stderr)
        raise
    return proc, url, log


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default=DEFAULT_HOST, help=f"bind address (default {DEFAULT_HOST})")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"bind port (default {DEFAULT_PORT})")
    p.add_argument("--ngrok", action="store_true", help="publish via ngrok (replaces any existing agent)")
    p.add_argument("--iso", type=Path, help="ISO to serve (default: newest in out/)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    iso = args.iso.resolve() if args.iso else latest_iso()
    if not iso.is_file():
        raise SystemExit(f"error: ISO not found: {iso}")
    sha256 = load_or_compute_sha256(iso)
    stage = build_stage(iso, sha256)
    Handler.iso_name = iso.name
    handler = lambda *a, **k: Handler(*a, directory=str(stage), **k)  # noqa: E731

    server = ThreadingHTTPServer((args.host, args.port), handler)
    local = f"http://{args.host}:{args.port}/"
    print(f"Serving {iso.name}", flush=True)
    print(f"Local   {local}", flush=True)
    print(f"ISO     {local}{iso.name}", flush=True)

    ngrok_proc = None
    if args.ngrok:
        if not shutil_which("ngrok"):
            raise SystemExit("error: ngrok is not on PATH")
        ngrok_proc, public, _log = start_ngrok(args.host, args.port)
        print(f"Public  {public}/", flush=True)
        print(f"ISO     {public}/{iso.name}", flush=True)
        print(
            "Browsers on the free ngrok URL see a splash first. "
            "curl/wget: add  -H 'ngrok-skip-browser-warning: 1'",
            flush=True,
        )

    print("Ctrl+C to stop.", flush=True)

    def shutdown(_signum=None, _frame=None):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.", flush=True)
    finally:
        server.server_close()
        if ngrok_proc is not None and ngrok_proc.poll() is None:
            ngrok_proc.send_signal(signal.SIGTERM)
            try:
                ngrok_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ngrok_proc.kill()
        # staging dir is under /tmp; leave it — small (symlinks + html)
    return 0


def shutil_which(name: str) -> str | None:
    from shutil import which
    return which(name)


if __name__ == "__main__":
    sys.exit(main())
