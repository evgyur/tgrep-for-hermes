import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tgrep_lifecycle.py"
spec = importlib.util.spec_from_file_location("tgrep_lifecycle", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def git_init(path):
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_index_paths_are_profile_local_and_outside_repo(tmp_path):
    repo = tmp_path / "repo"
    git_init(repo)
    default = tmp_path / "default-home"
    dev = tmp_path / "dev-home"
    default.mkdir()
    dev.mkdir()
    root = mod.canonical_repo(repo)
    a = mod.index_path(default, root)
    b = mod.index_path(dev, root)
    assert a != b
    assert repo not in a.parents
    assert repo not in b.parents
    assert a.parts[-3:-1] == ("tgrep-code-search", "indexes")


def test_subdirectory_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    git_init(repo)
    sub = repo / "sub"
    sub.mkdir()
    try:
        mod.canonical_repo(sub)
    except RuntimeError as exc:
        assert "exact Git top-level" in str(exc)
    else:
        raise AssertionError("subdirectory unexpectedly accepted")


def test_user_service_is_profile_templated_and_network_confined():
    text = mod.unit_text()
    assert "hermes-tgrep@" not in text
    assert "EnvironmentFile=%h/.config/hermes-tgrep/%i.env" in text
    assert "ExecStart=/usr/bin/env -- ${TGREP_BINARY} serve ${TGREP_ROOT} --index-path ${TGREP_INDEX}" in text
    assert "IPAddressDeny=any" in text
    assert "IPAddressAllow=localhost" in text
    assert "Restart=on-failure" in text


def test_start_restarts_existing_instance_after_rewriting_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "prepare", lambda args: {"binary": "/tmp/tgrep"})
    monkeypatch.setattr(mod, "install_unit", lambda: Path("/tmp/hermes-tgrep@.service"))
    monkeypatch.setattr(mod, "status", lambda args: {"healthy": True})
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, check: calls.append(command),
    )
    args = type("Args", (), {"profile": "example"})()

    result = mod.start(args)

    assert result["unit"] == "hermes-tgrep@example.service"
    assert result["readiness"] == {"healthy": True}
    assert calls == [
        ["systemctl", "--user", "enable", "hermes-tgrep@example.service"],
        ["systemctl", "--user", "restart", "hermes-tgrep@example.service"],
    ]


def test_start_stops_unready_instance_and_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "prepare", lambda args: {})
    monkeypatch.setattr(mod, "install_unit", lambda: Path("/tmp/hermes-tgrep@.service"))
    monkeypatch.setattr(mod, "status", lambda args: {"healthy": False})
    ticks = iter((0.0, 31.0))
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda command, check: calls.append((command, check)),
    )
    args = type("Args", (), {"profile": "example"})()

    try:
        mod.start(args)
    except RuntimeError as exc:
        assert "readiness" in str(exc)
    else:
        raise AssertionError("unready service unexpectedly accepted")

    assert calls[-1] == (["systemctl", "--user", "stop", "hermes-tgrep@example.service"], False)
