#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
forbidden = [
    r"/home/[A-Za-z0-9._-]+",
    r"TELEGRAM_SESSION_STRING",
    r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY",
    r"(?:gh[opusr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
    r"(?:api[_-]?key|token|password)\s*[:=]\s*['\"][^'\"]{8,}",
]
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in {".git", ".ruff_cache", "__pycache__"} for part in path.parts) or path.resolve() == Path(__file__).resolve():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in forbidden:
        if re.search(pattern, text, re.I):
            raise SystemExit(f"public hygiene violation in {path.relative_to(ROOT)}: {pattern}")
print("public hygiene: ok")
