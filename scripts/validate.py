#!/usr/bin/env python3
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
skill = (root / "SKILL.md").read_text(encoding="utf-8")
required_text = [
    "optional profile-scoped backend",
    "broad/high-volume",
    "immediate post-write truth",
    "register_search_backend",
    "loopback",
    "backend=tgrep",
    "references/operator.md",
]
required_files = [
    "plugin.yaml", "__init__.py", "tgrep_backend.py", "references/operator.md",
    "scripts/tgrep_lifecycle.py", "tests/test_tgrep_backend.py",
]
errors = [f"missing contract: {item}" for item in required_text if item not in skill]
errors += [f"missing file: {item}" for item in required_files if not (root / item).is_file()]
if not re.search(r"^name: tgrep-for-hermes$", skill, re.M):
    errors.append("bad or missing skill name")
if not re.search(r"^description: .+", skill, re.M):
    errors.append("missing skill description")
if len(skill) > 12000:
    errors.append("skill exceeds 12 KB budget")
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("tgrep-for-hermes contract: ok")
