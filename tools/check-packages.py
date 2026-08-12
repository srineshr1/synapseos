#!/usr/bin/env python3
"""Pre-flight check for archiso/packages.x86_64.

Resolves the package list against the real core/extra databases plus the local
[synapseos-local] repo, without needing root or a pacman transaction. Reports
unknown packages, unsatisfied dependencies, conflicts inside the selection and
the total installed size of the resulting root filesystem.

    python3 tools/check-packages.py

Exit status is non-zero if anything would make `pacstrap` fail.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES_FILE = ROOT / "archiso/packages.x86_64"
AIROOTFS = ROOT / "archiso/airootfs"
LOCAL_REPO = ROOT / "archiso/repo"
CACHE = Path.home() / ".cache/synapseos-depcheck/db"
MIRRORLIST = Path("/etc/pacman.d/mirrorlist")
REPOS = ("core", "extra")
DEP_SPLIT = re.compile(r"[<>=:]")


def mirrors() -> list[str]:
    servers = []
    if MIRRORLIST.exists():
        for line in MIRRORLIST.read_text().splitlines():
            line = line.strip()
            if line.startswith("Server"):
                servers.append(line.split("=", 1)[1].strip())
    # Always keep a known-good fallback: some mirrors reject non-pacman clients.
    servers.append("https://geo.mirror.pkgbuild.com/$repo/os/$arch")
    return servers


def fetch_db(repo: str, ext: str = "db") -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / f"{repo}.{ext}"
    if dest.exists():
        return dest
    errors = []
    for server in mirrors():
        url = server.replace("$repo", repo).replace("$arch", "x86_64") + f"/{repo}.{ext}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "pacman/7"})
            with urllib.request.urlopen(request, timeout=120) as r:
                data = r.read()
        except Exception as exc:  # try the next mirror
            errors.append(f"{url}: {exc}")
            continue
        dest.write_bytes(data)
        print(f"  fetched {repo}.{ext} from {server.split('/$')[0]} ({len(data) / 1e6:.1f} MB)")
        return dest
    raise SystemExit("could not download {}.{}:\n  ".format(repo, ext) + "\n  ".join(errors))


def parse_db(path: Path, repo: str, index: dict, provides: dict, groups: dict) -> None:
    with tarfile.open(path) as tar:
        for member in tar:
            if not member.name.endswith("/desc"):
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            fields, key = {}, None
            for raw in handle.read().decode().splitlines():
                if raw.startswith("%") and raw.endswith("%"):
                    key = raw.strip("%")
                    fields[key] = []
                elif raw and key:
                    fields[key].append(raw)
            name = fields.get("NAME", [None])[0]
            if not name:
                continue
            entry = {
                "name": name,
                "repo": repo,
                "filename": fields.get("FILENAME", [""])[0],
                "version": fields.get("VERSION", [""])[0],
                "depends": fields.get("DEPENDS", []),
                "conflicts": fields.get("CONFLICTS", []),
                "provides": fields.get("PROVIDES", []),
                "replaces": fields.get("REPLACES", []),
                "isize": int(fields.get("ISIZE", [0])[0] or 0),
            }
            index.setdefault(name, entry)
            for item in entry["provides"]:
                provides.setdefault(DEP_SPLIT.split(item)[0], set()).add(name)
            for group in fields.get("GROUPS", []):
                groups.setdefault(group, set()).add(name)


def version_matches(version: str, op: str, target: str) -> bool:
    """True if `version op target` holds, using pacman's own vercmp."""
    result = int(
        subprocess.run(
            ["vercmp", version, target], capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    return {
        "<": result < 0,
        "<=": result <= 0,
        "=": result == 0,
        ">=": result >= 0,
        ">": result > 0,
    }[op]


def backup_files(entry: dict) -> set[str] | None:
    """The package's `backup` array, or None if it could not be determined.

    pacman does not treat a pre-existing file as a conflict when the incoming
    package lists it as a backup file (that is how archiso can ship /etc/passwd
    and /etc/default/grub). The sync databases do not carry the backup array, so
    read it out of the package's .PKGINFO - the first member of the archive,
    which makes a 128 KiB range request enough.
    """
    local = sorted(Path("/var/lib/pacman/local").glob(f"{entry['name']}-*/files"))
    for candidate in local:
        text = candidate.read_text(errors="replace")
        if "%BACKUP%" in text:
            section = text.split("%BACKUP%", 1)[1].split("%", 1)[0]
            return {line.split("\t")[0] for line in section.split() if line}
        return set()

    filename = entry.get("filename")
    if not filename:
        return None
    for server in mirrors():
        url = server.replace("$repo", entry["repo"]).replace("$arch", "x86_64") + f"/{filename}"
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "pacman/7", "Range": "bytes=0-131071"}
            )
            with urllib.request.urlopen(request, timeout=60) as r:
                head = r.read(131072)
        except Exception:
            continue
        # bsdtar exits non-zero on the truncated tail; .PKGINFO comes first.
        result = subprocess.run(
            ["bsdtar", "-xOf", "-", ".PKGINFO"], input=head, capture_output=True
        )
        info = result.stdout.decode(errors="replace")
        if "pkgname" not in info:
            continue
        return {
            line.split("=", 1)[1].strip()
            for line in info.splitlines()
            if line.startswith("backup")
        }
    return None


def airootfs_paths() -> dict[str, Path]:
    """Every regular file the profile overlays onto the root filesystem.

    Keys are package-database style paths (no leading slash), which is what the
    *.files databases contain.
    """
    result = {}
    if not AIROOTFS.is_dir():
        return result
    for path in AIROOTFS.rglob("*"):
        if path.is_file() or path.is_symlink():
            result[str(path.relative_to(AIROOTFS))] = path
    return result


def file_owners(paths: set[str], selected: set[str]) -> dict[str, list[str]]:
    """Map each path to the selected packages that also ship it.

    mkarchiso copies airootfs/ into the pacstrap dir *before* running pacstrap,
    so any path that a package owns makes pacman abort the whole build with
    "<pkg>: /path exists in filesystem". Only packages that are actually being
    installed matter, hence the `selected` filter.
    """
    owners: dict[str, list[str]] = {}
    for repo in REPOS:
        db = fetch_db(repo, "files")
        with tarfile.open(db) as tar:
            for member in tar:
                if not member.name.endswith("/files"):
                    continue
                pkgdir = member.name.rsplit("/", 1)[0]
                name = pkgdir.rsplit("-", 2)[0]
                if name not in selected:
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                for raw in handle.read().decode(errors="replace").splitlines():
                    if raw.startswith("%") or not raw or raw.endswith("/"):
                        continue
                    if raw in paths:
                        owners.setdefault(raw, []).append(name)
    return owners


def read_package_list() -> list[str]:
    """Mirror how mkarchiso parses the file: strip comments and blank lines."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else PACKAGES_FILE
    wanted = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            wanted.append(line)
    return wanted


def main() -> int:
    index: dict[str, dict] = {}
    provides: dict[str, set] = {}
    groups: dict[str, set] = {}

    print("Loading databases...")
    for repo in REPOS:
        parse_db(fetch_db(repo), repo, index, provides, groups)
    local_db = LOCAL_REPO / "synapseos-local.db.tar.gz"
    if local_db.exists():
        parse_db(local_db, "synapseos-local", index, provides, groups)
    else:
        print(f"  WARNING: {local_db} is missing; run tools/build-aur.sh")
    print(f"  {len(index)} packages known\n")

    wanted = read_package_list()
    unknown, selected, queue = [], {}, []

    for name in wanted:
        if name in index:
            queue.append(name)
        elif name in groups:
            queue.extend(sorted(groups[name]))
            print(f"note: '{name}' is a group -> {len(groups[name])} packages")
        elif name in provides:
            queue.extend(sorted(provides[name]))
        else:
            unknown.append(name)

    unsatisfied = []
    while queue:
        name = queue.pop()
        if name in selected:
            continue
        entry = index.get(name)
        if entry is None:
            unknown.append(name)
            continue
        selected[name] = entry
        for dep in entry["depends"]:
            base = DEP_SPLIT.split(dep)[0]
            if base in index:
                queue.append(base)
            elif base in provides:
                queue.append(sorted(provides[base])[0])
            else:
                unsatisfied.append((name, dep))

    # Conflicts between two packages that are both in the selection. Version
    # bounds matter: cryptsetup declares `conflicts=mkinitcpio<38-1`, which is
    # not a conflict at all with a current mkinitcpio.
    clashes = []
    for name, entry in selected.items():
        for conflict in entry["conflicts"]:
            match = re.match(r"^([^<>=]+)(<=|>=|<|>|=)(.+)$", conflict)
            base = match.group(1) if match else conflict
            if base not in selected or base == name:
                continue
            if match and not version_matches(
                selected[base]["version"], match.group(2), match.group(3)
            ):
                continue
            clashes.append((name, base))

    total = sum(e["isize"] for e in selected.values())
    print(f"requested        : {len(wanted)}")
    print(f"with dependencies: {len(selected)}")
    print(f"installed size   : {total / 1e9:.2f} GB")

    # Files the profile overlays that a to-be-installed package also owns.
    overlay = airootfs_paths()
    print(f"\nChecking {len(overlay)} airootfs files against the package file lists...")
    candidates = file_owners(set(overlay), set(selected))

    # A path both sides ship is only fatal when the package does not list it as
    # a backup file.
    file_clashes: dict[str, list[str]] = {}
    unverified: dict[str, list[str]] = {}
    backups: dict[str, set[str] | None] = {}
    for path, pkgs in candidates.items():
        for pkg in sorted(set(pkgs)):
            if pkg not in backups:
                backups[pkg] = backup_files(selected[pkg])
            listed = backups[pkg]
            if listed is None:
                unverified.setdefault(path, []).append(pkg)
            elif path not in listed:
                file_clashes.setdefault(path, []).append(pkg)

    ok = True
    if unknown:
        ok = False
        print(f"\nUNKNOWN PACKAGES ({len(unknown)}):")
        for name in sorted(set(unknown)):
            print(f"  {name}")
    if unsatisfied:
        ok = False
        print(f"\nUNSATISFIED DEPENDENCIES ({len(unsatisfied)}):")
        for name, dep in sorted(set(unsatisfied)):
            print(f"  {name} requires {dep}")
    if clashes:
        ok = False
        print(f"\nCONFLICTS ({len(clashes)}):")
        for a, b in sorted({tuple(sorted(c)) for c in clashes}):
            print(f"  {a} <-> {b}")
    if file_clashes:
        ok = False
        print(f"\nFILE CONFLICTS WITH airootfs/ ({len(file_clashes)}):")
        for path, pkgs in sorted(file_clashes.items()):
            print(f"  /{path} is also shipped by {', '.join(sorted(set(pkgs)))}")
        print("  pacstrap aborts with '<pkg>: /path exists in filesystem'.")
        print("  Rename the profile's copy or drop the package.")
    if unverified:
        print(f"\nairootfs files shared with a package, backup array unknown ({len(unverified)}):")
        for path, pkgs in sorted(unverified.items()):
            print(f"  /{path} <- {', '.join(sorted(set(pkgs)))}")

    print("\nOK: pacstrap should resolve this package list." if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
