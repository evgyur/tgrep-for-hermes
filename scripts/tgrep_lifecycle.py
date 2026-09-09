#!/usr/bin/env python3
"""Prepare and operate profile-local tgrep indexes under systemd --user."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SERVICE_NAME = "hermes-tgrep@.service"


def canonical_repo(path: Path) -> Path:
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("root is not a Git repository")
    root = Path(proc.stdout.strip()).resolve(strict=True)
    if path.resolve(strict=True) != root:
        raise RuntimeError(f"root must be the exact Git top-level: {root}")
    return root


def root_key(root: Path) -> str:
    return hashlib.sha256(os.fsencode(str(root))).hexdigest()[:24]


def index_path(home: Path, root: Path) -> Path:
    return home.resolve(strict=True) / "plugin-data" / "tgrep-code-search" / "indexes" / root_key(root)


def unit_text() -> str:
    return """[Unit]
Description=Hermes profile tgrep server (%i)
After=default.target

[Service]
Type=simple
EnvironmentFile=%h/.config/hermes-tgrep/%i.env
ExecStart=/usr/bin/env -- ${TGREP_BINARY} serve ${TGREP_ROOT} --index-path ${TGREP_INDEX}
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
IPAddressDeny=any
IPAddressAllow=localhost
LockPersonality=true

[Install]
WantedBy=default.target
"""


def write_atomic(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def paths(args) -> tuple[Path, Path, Path, Path]:
    if not PROFILE_RE.fullmatch(args.profile):
        raise RuntimeError("invalid profile name")
    home = Path(args.hermes_home).expanduser().resolve(strict=True)
    root = canonical_repo(Path(args.root).expanduser())
    binary = Path(args.binary).expanduser().resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("tgrep binary is missing or not executable")
    index = index_path(home, root)
    return home, root, binary, index


def env_line(name: str, value: Path) -> str:
    return f"{name}={shlex.quote(str(value))}\n"


def prepare(args) -> dict:
    home, root, binary, index = paths(args)
    index.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(binary), "index", str(root), "--index-path", str(index)],
        text=True, capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "tgrep index failed")
    metadata = {
        "schema": 1,
        "profile": args.profile,
        "hermes_home": str(home),
        "root": str(root),
        "index": str(index),
        "binary": str(binary),
    }
    write_atomic(index / "root.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    env_dir = Path.home() / ".config" / "hermes-tgrep"
    env_path = env_dir / f"{args.profile}.env"
    write_atomic(env_path, "".join([
        env_line("TGREP_BINARY", binary), env_line("TGREP_ROOT", root), env_line("TGREP_INDEX", index),
    ]))
    return {**metadata, "env_file": str(env_path), "index_stdout": proc.stdout.strip()}


def install_unit() -> Path:
    unit = Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME
    write_atomic(unit, unit_text(), mode=0o644)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    return unit


def start(args) -> dict:
    result = prepare(args)
    result["unit_file"] = str(install_unit())
    unit = f"hermes-tgrep@{args.profile}.service"
    subprocess.run(["systemctl", "--user", "enable", unit], check=True)
    # prepare() rewrites this profile's environment file. Restart an existing
    # instance so it cannot keep serving a previous root/binary/index tuple.
    subprocess.run(["systemctl", "--user", "restart", unit], check=True)
    result["unit"] = unit
    deadline = time.monotonic() + 30.0
    while True:
        readiness = status(args)
        if readiness["healthy"]:
            result["readiness"] = readiness
            return result
        if time.monotonic() >= deadline:
            subprocess.run(["systemctl", "--user", "stop", unit], check=False)
            raise RuntimeError("tgrep server did not reach watcher/reconcile readiness")
        time.sleep(0.2)


def stop(args) -> dict:
    if not PROFILE_RE.fullmatch(args.profile):
        raise RuntimeError("invalid profile name")
    unit = f"hermes-tgrep@{args.profile}.service"
    proc = subprocess.run(["systemctl", "--user", "stop", unit], check=False)
    return {"unit": unit, "stopped": proc.returncode == 0, "indexes_deleted": False}


def status(args) -> dict:
    home, root, binary, index = paths(args)
    proc = subprocess.run(
        [str(binary), "status", str(root), "--index-path", str(index)],
        text=True, capture_output=True, check=False,
    )
    text = proc.stdout + proc.stderr
    required = (
        "Server status for ", "Watcher:    active", "Reconcile:  idle",
        "Reconcile pending: no", "Reconcile overdue: no", "Indexing:   complete",
    )
    healthy = proc.returncode == 0 and all(token in text for token in required)
    return {
        "profile": args.profile, "hermes_home": str(home), "root": str(root), "index": str(index),
        "healthy": healthy, "status_exit": proc.returncode, "status": text.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "start", "status", "stop"))
    parser.add_argument("--profile", required=True)
    parser.add_argument("--hermes-home")
    parser.add_argument("--root")
    parser.add_argument("--binary", default="~/.local/bin/tgrep")
    args = parser.parse_args()
    if args.action != "stop" and (not args.hermes_home or not args.root):
        parser.error("--hermes-home and --root are required")
    try:
        result = globals()[args.action](args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
