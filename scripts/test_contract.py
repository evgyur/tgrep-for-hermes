#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile

validator = Path(__file__).with_name("validate.py")
subprocess.run(["python3", str(validator)], check=True)
source = validator.read_text(encoding="utf-8")
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "scripts").mkdir()
    (root / "references").mkdir()
    original = validator.resolve().parents[1]
    text = (original / "SKILL.md").read_text(encoding="utf-8").replace("register_search_backend", "")
    (root / "SKILL.md").write_text(text, encoding="utf-8")
    for relative in (
        "plugin.yaml", "__init__.py", "tgrep_backend.py", "references/operator.md",
        "scripts/tgrep_lifecycle.py", "tests/test_tgrep_backend.py",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture", encoding="utf-8")
    candidate = source.replace("Path(__file__).resolve().parents[1]", "Path(" + repr(str(root)) + ")")
    probe = root / "scripts" / "validate.py"
    probe.write_text(candidate, encoding="utf-8")
    result = subprocess.run(["python3", str(probe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        raise SystemExit("negative contract test unexpectedly passed")
print("tgrep-for-hermes negative contract: ok")
