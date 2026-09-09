#!/usr/bin/env python3
from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]
for path in ROOT.rglob("*.py"):
    if ".git" not in path.parts:
        py_compile.compile(str(path), doraise=True)
for path in ROOT.rglob("*.sh"):
    raise SystemExit(f"unexpected shell script without syntax policy: {path.relative_to(ROOT)}")
print("script syntax: ok")
