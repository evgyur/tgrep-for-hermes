import json
import os
from pathlib import Path

import pytest
from hermes_cli.search_backends import SearchBackendRequest

import tgrep_backend as mod


@pytest.fixture
def root(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    binary = tmp_path / "tgrep"
    binary.write_text("binary")
    binary.chmod(0o755)
    data = tmp_path / "data"
    index = data / "indexes" / mod._root_key(repo)
    index.mkdir(parents=True)
    (index / "root.json").write_text(json.dumps({"root": str(repo)}))
    monkeypatch.setattr(mod, "_plugin_data_dir", lambda: data)
    monkeypatch.setattr(mod, "_canonical_git_root", lambda path: repo if Path(path).resolve() == repo else None)
    monkeypatch.setattr(mod, "_loopback_listener", lambda pid, port: True)
    return repo, binary, index


def backend(root, **overrides):
    repo, binary, _ = root
    values = {
        "enabled": True, "binary": binary, "repo_roots": [str(repo)], "min_literal_length": 8,
        "max_limit": 100, "broad_match_threshold": 200, "freshness_quarantine_seconds": 3,
        "command_timeout_seconds": 5,
    }
    values.update(overrides)
    return mod.TgrepBackend(**values)


def request(root, **overrides):
    values = {
        "pattern": "UniqueSymbol", "path": str(root[0]), "file_glob": None, "limit": 50, "offset": 0,
        "output_mode": "content", "context": 0, "environment_kind": "local", "is_local": True,
        "cwd": str(root[0]),
    }
    values.update(overrides)
    return SearchBackendRequest(**values)


def healthy_status():
    return b"""Server status for /repo
  PID:        123
  Port:       4321
  Watcher:    active
  Watch mode: native (requested: auto)
  Reconcile:  idle
  Reconcile pending: no
  Reconcile overdue: no
  Last successful reconcile: 1s ago
  Indexing:   complete
"""


def test_selective_literal_routes_to_tgrep(root, monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if "status" in argv:
            return 0, healthy_status(), b"", None
        return 0, f"{root[0]}/a.py:7:UniqueSymbol\n".encode(), b"", None

    monkeypatch.setattr(mod, "_run_bounded", run)
    result = backend(root).search(request(root))

    assert result.backend == "tgrep"
    assert result.route_reason == "eligible_selective_literal"
    assert result.matches[0].line_number == 7
    assert "-F" in calls[-1]
    assert calls[-1][-2:] == ["UniqueSymbol", str(root[0])]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"pattern": "def"}, "broad_query"),
        ({"pattern": "Unique.*Symbol"}, "regex_query"),
        ({"context": 2}, "unsupported_semantics"),
        ({"output_mode": "count"}, "unsupported_semantics"),
        ({"file_glob": "!secret/**"}, "unsupported_glob"),
        ({"is_local": False}, "unsupported_environment"),
    ],
)
def test_unsupported_requests_decline_without_spawning(root, monkeypatch, kwargs, reason):
    monkeypatch.setattr(mod, "_run_bounded", lambda *a, **k: pytest.fail("must not spawn"))
    result = backend(root).search(request(root, **kwargs))
    assert result.route_reason == reason


def test_missing_unhealthy_or_diagnostic_falls_back(root, monkeypatch):
    b = backend(root)
    monkeypatch.setattr(mod, "_run_bounded", lambda *a, **k: (2, b"", b"boom", None))
    assert b.search(request(root)).route_reason == "unhealthy_server"

    calls = 0
    def diagnostic(argv, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 0, healthy_status(), b"", None
        return 2, b"", b"Server unreachable", None
    monkeypatch.setattr(mod, "_run_bounded", diagnostic)
    assert b.search(request(root)).route_reason == "tgrep_diagnostic"


def test_post_write_and_terminal_force_immediate_native_fallback(root):
    b = backend(root)
    b.observe_tool_call(tool_name="write_file", status="ok")
    assert b.search(request(root)).route_reason == "post_write_freshness"

    b._fresh_until = 0
    b.observe_tool_call(tool_name="terminal", status="ok")
    assert b.search(request(root)).route_reason == "post_write_freshness"

    b._fresh_until = 0
    b.observe_tool_call(tool_name="patch", status="error")
    assert b.search(request(root)).route_reason == "post_write_freshness"


def test_non_linux_listener_check_fails_closed(monkeypatch):
    monkeypatch.setattr(mod.os, "name", "nt")
    assert not mod._loopback_listener(123, 4321)


def test_broad_result_volume_and_invalid_output_fall_back(root, monkeypatch):
    b = backend(root, broad_match_threshold=2)
    outputs = iter([
        (0, healthy_status(), b"", None),
        (0, b"a.py:1:x\na.py:2:x\na.py:3:x\n", b"", None),
    ])
    monkeypatch.setattr(mod, "_run_bounded", lambda *a, **k: next(outputs))
    assert b.search(request(root)).route_reason == "broad_result_volume"

    outputs = iter([(0, healthy_status(), b"", None), (0, b"not-parseable\n", b"", None)])
    monkeypatch.setattr(mod, "_run_bounded", lambda *a, **k: next(outputs))
    assert b.search(request(root)).route_reason == "incompatible_output"


def test_linux_listener_requires_pid_ownership_and_ipv4_ipv6_loopback(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    (proc / "123" / "fd").mkdir(parents=True)
    os.symlink("socket:[77]", proc / "123" / "fd" / "4")
    rows = [("127.0.0.1", 4321, "77")]
    monkeypatch.setattr(mod, "_tcp_listeners", lambda: rows)
    assert mod._linux_loopback_listener(123, 4321, proc)

    rows.append(("::", 4321, "77"))
    assert not mod._linux_loopback_listener(123, 4321, proc)
    rows[:] = [("127.0.0.1", 4321, "88")]
    assert not mod._linux_loopback_listener(123, 4321, proc)


def test_live_listener_validation_without_hostwide_proc_tables(monkeypatch):
    import socket
    original = Path.read_text

    def no_tcp_tables(path, *args, **kwargs):
        if str(path) in {"/proc/net/tcp", "/proc/net/tcp6"}:
            raise OSError("host-wide TCP table reads are unavailable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", no_tcp_tables)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert mod._linux_loopback_listener(os.getpid(), port)
        assert not mod._linux_loopback_listener(2147483647, port)
    assert not mod._linux_loopback_listener(os.getpid(), port)


def test_live_listener_rejects_wildcard_bind():
    import socket
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen()
        assert not mod._linux_loopback_listener(os.getpid(), listener.getsockname()[1])


@pytest.mark.parametrize("fault", ["interrupted", "truncated", "wrong_peer", "error", "short", "timeout"])
def test_incomplete_kernel_dump_never_proves_listener_ownership(monkeypatch, fault):
    import socket
    import struct

    class BrokenDump:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, value):
            pass

        def sendto(self, *args):
            pass

        def recvmsg(self, size):
            if fault == "timeout":
                raise TimeoutError()
            packet = struct.pack("=IHHIIi", 20, 2 if fault == "error" else 3, 0x10 if fault == "interrupted" else 0, 1, 0, -1 if fault == "error" else 0)
            return (b"short" if fault == "short" else packet, [], socket.MSG_TRUNC if fault == "truncated" else 0, (123 if fault == "wrong_peer" else 0, 0))

    monkeypatch.setattr(mod.socket, "socket", lambda *a: BrokenDump())
    with pytest.raises((ValueError, OSError)):
        mod._tcp_listeners()
    assert not mod._linux_loopback_listener(os.getpid(), 54321)
