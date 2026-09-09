#!/usr/bin/env python3
from pathlib import Path
import re, sys

root = Path(__file__).resolve().parents[1]
skill = (root / "SKILL.md").read_text(encoding="utf-8")
ref = root / "references" / "operator.md"
required = [
    "specialized indexed search path",
    "broad/high-volume",
    "on-disk index is a snapshot",
    "Exit `0` means matches, `1` means no matches, and `2` means error",
    "references/operator.md",
    "Do not modify Hermes core",
]
errors = [f"missing contract: {x}" for x in required if x not in skill]
if not re.search(r"^name: tgrep-for-hermes$", skill, re.M): errors.append("bad or missing name")
if not re.search(r"^description: .+", skill, re.M): errors.append("missing description")
if not ref.is_file(): errors.append("missing operator reference")
if len(skill) > 12000: errors.append("root exceeds 12 KB budget")
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("tgrep-for-hermes contract: ok")
