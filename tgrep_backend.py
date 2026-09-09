"""Conservative tgrep router for Hermes' protected search backend seam."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import socket
import struct
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    from hermes_cli.search_backends import (
        SearchBackendDecline,
        SearchBackendMatch,
        SearchBackendRequest,
        SearchBackendResult,
    )
except ImportError:  # fail safely on Hermes releases without the generic seam
    SearchBackendDecline = SearchBackendMatch = SearchBackendRequest = SearchBackendResult = None  # type: ignore

_PLUGIN_ID = "tgrep-code-search"
_REGEX_META = frozenset(".\\^$*+?{}[]|()")
_SAFE_GLOB = re.compile(r"^(?:\*|\*\*/\*)\.[A-Za-z0-9_+-]{1,24}$")
_STATUS_PID = re.compile(r"^\s*PID:\s*(\d+)\s*$", re.MULTILINE)
_STATUS_PORT = re.compile(r"^\s*Port:\s*(\d+)\s*$", re.MULTILINE)
_LINE = re.compile(r"^(.*?):(\d+):(.*)$")


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _root_key(root: Path) -> str:
    return hashlib.sha256(os.fsencode(str(root))).hexdigest()[:24]


def _plugin_data_dir() -> Path:
    from plugins.plugin_storage import plugin_data_dir

    return plugin_data_dir(_PLUGIN_ID)


def index_dir_for_root(root: Path) -> Path:
    return _plugin_data_dir() / "indexes" / _root_key(root)


def _canonical_git_root(path: Path) -> Path | None:
    try:
        candidate = path.expanduser().resolve(strict=True)
    except OSError:
        return None
    if not candidate.is_dir():
        return None
    try:
        run = subprocess.run(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True, timeout=2, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if run.returncode != 0 or run.stderr:
        return None
    try:
        root = Path(run.stdout.strip()).resolve(strict=True)
    except OSError:
        return None
    return root if root == candidate else None


def _tcp_listeners() -> list[tuple[str, int, str]]:
    """Fresh, bounded Linux SOCK_DIAG dump; no host-wide /proc TCP scan.

    Wire layouts are Linux UAPI inet_diag_req_v2 / inet_diag_msg. Request
    LISTEN only, without optional attributes. Reject incomplete/error dumps.
    """
    listeners = []
    deadline = time.monotonic() + 1.0
    remaining_bytes = 1024 * 1024
    for family in (socket.AF_INET, socket.AF_INET6):
        with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 4) as diag:
            diag.settimeout(max(0.001, deadline - time.monotonic()))
            request = struct.pack("=BBBBI", family, socket.IPPROTO_TCP, 0, 0, 1 << 10)
            request += bytes(40) + b"\xff" * 8  # sockid, INET_DIAG_NOCOOKIE
            diag.sendto(struct.pack("=IHHII", 16 + len(request), 20, 0x301, 1, 0) + request, (0, 0))
            done = False
            while not done:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or remaining_bytes <= 0:
                    raise ValueError("SOCK_DIAG budget exhausted")
                diag.settimeout(remaining)
                packet, _, recv_flags, peer = diag.recvmsg(65536)
                remaining_bytes -= len(packet)
                if peer[0] != 0 or recv_flags & socket.MSG_TRUNC or not packet or remaining_bytes < 0:
                    raise ValueError("Incomplete SOCK_DIAG datagram")
                pos = 0
                while pos < len(packet):
                    if len(packet) - pos < 16:
                        raise ValueError("Short SOCK_DIAG header")
                    length, kind, flags, sequence, _ = struct.unpack_from("=IHHII", packet, pos)
                    if length < 16 or pos + length > len(packet) or sequence != 1 or flags & 0x10:
                        raise ValueError("Invalid or interrupted SOCK_DIAG dump")
                    body = packet[pos + 16:pos + length]
                    if kind == 3:  # NLMSG_DONE
                        if body and (len(body) < 4 or struct.unpack_from("=i", body)[0]):
                            raise ValueError("SOCK_DIAG completion error")
                        done = True
                    elif kind == 20 and len(body) >= 72 and body[0] == family and body[1] == 10:
                        address = socket.inet_ntop(family, body[8:12] if family == socket.AF_INET else body[8:24])
                        listeners.append((address, struct.unpack_from("!H", body, 4)[0], str(struct.unpack_from("=I", body, 68)[0])))
                    else:
                        raise ValueError("Unexpected SOCK_DIAG response")
                    pos += (length + 3) & ~3
    return listeners


def _linux_loopback_listener(pid: int, port: int, proc_root: Path = Path("/proc")) -> bool:
    """Bind every TCP listener for ``port`` to ``pid`` and a loopback address."""
    try:
        owned = set()
        for fd in (proc_root / str(pid) / "fd").iterdir():
            try:
                target = os.readlink(fd)
            except FileNotFoundError:  # descriptor closed after enumeration
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                owned.add(target[8:-1])
        listeners = [(address, inode) for address, number, inode in _tcp_listeners() if number == port]
        return bool(listeners) and all(address in {"127.0.0.1", "::1"} and inode in owned for address, inode in listeners)
    except (OSError, ValueError):
        return False


def _loopback_listener(pid: int, port: int) -> bool:
    """Verify exclusive loopback binding and, on Linux, socket ownership."""
    if os.name != "posix" or not Path("/proc/net/tcp").exists():
        # Reachability alone cannot prove exclusive loopback binding or socket
        # ownership. Unsupported hosts therefore fail closed to native rg.
        return False
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
        if b"tgrep" not in cmdline or b"serve" not in cmdline:
            return False
        return _linux_loopback_listener(pid, port)
    except (OSError, ValueError):
        return False


def _run_bounded(
    argv: list[str], *, timeout: float, max_stdout: int, max_stderr: int,
    max_lines: int | None = None,
) -> tuple[int, bytes, bytes, str | None]:
    """Run without a shell and cap both pipes; a cap/timeout is a fallback, never partial evidence."""
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        return 127, b"", str(exc).encode(), "spawn_error"
    selector = selectors.DefaultSelector()
    assert proc.stdout is not None and proc.stderr is not None
    selector.register(proc.stdout, selectors.EVENT_READ, "out")
    selector.register(proc.stderr, selectors.EVENT_READ, "err")
    chunks = {"out": bytearray(), "err": bytearray()}
    deadline = time.monotonic() + timeout
    reason = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "timeout"
                break
            events = selector.select(min(remaining, 0.1))
            if not events and proc.poll() is not None:
                break
            for key, _ in events:
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                target = chunks[key.data]
                target.extend(data)
                cap = max_stdout if key.data == "out" else max_stderr
                if len(target) > cap:
                    reason = f"{key.data}put_limit"
                    break
                if key.data == "out" and max_lines is not None and target.count(b"\n") >= max_lines:
                    reason = "line_limit"
                    break
            if reason:
                break
    finally:
        if reason and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=1)
        selector.close()
    return int(proc.returncode or 0), bytes(chunks["out"]), bytes(chunks["err"]), reason


class TgrepBackend:
    def __init__(
        self, *, enabled: bool, binary: Path, repo_roots: Iterable[str],
        min_literal_length: int, max_limit: int, broad_match_threshold: int,
        freshness_quarantine_seconds: float, command_timeout_seconds: float,
    ) -> None:
        self.enabled = enabled
        self.binary = binary.expanduser().resolve(strict=False)
        self.repo_roots = {
            root for value in repo_roots
            if isinstance(value, str) and (root := _canonical_git_root(Path(value))) is not None
        }
        self.min_literal_length = min_literal_length
        self.max_limit = max_limit
        self.broad_match_threshold = broad_match_threshold
        self.freshness_quarantine_seconds = freshness_quarantine_seconds
        self.command_timeout_seconds = command_timeout_seconds
        self._fresh_until = 0.0

    @classmethod
    def from_context(cls, ctx):
        roots = ctx.get_config("repo_roots", [])
        return cls(
            enabled=bool(ctx.get_config("enabled", False)),
            binary=Path(str(ctx.get_config("binary", "~/.local/bin/tgrep"))),
            repo_roots=roots if isinstance(roots, list) else [],
            min_literal_length=_int(ctx.get_config("min_literal_length", 8), 8, 3, 256),
            max_limit=_int(ctx.get_config("max_limit", 100), 100, 1, 1000),
            broad_match_threshold=_int(ctx.get_config("broad_match_threshold", 200), 200, 2, 10000),
            freshness_quarantine_seconds=_float(ctx.get_config("freshness_quarantine_seconds", 3.0), 3.0, 0.1, 300.0),
            command_timeout_seconds=_float(ctx.get_config("command_timeout_seconds", 5.0), 5.0, 0.25, 60.0),
        )

    def observe_tool_call(self, tool_name: str = "", status: str = "", **_: Any) -> None:
        if tool_name in {"write_file", "patch", "terminal"}:
            self._fresh_until = max(
                self._fresh_until,
                time.monotonic() + self.freshness_quarantine_seconds,
            )

    def _eligible(self, request) -> tuple[Path | None, str | None]:
        if not self.enabled:
            return None, "disabled"
        if not request.is_local:
            return None, "unsupported_environment"
        if request.output_mode not in {"content", "files_only"} or request.context:
            return None, "unsupported_semantics"
        if request.offset < 0 or request.limit > self.max_limit:
            return None, "broad_query"
        if len(request.pattern) < self.min_literal_length:
            return None, "broad_query"
        if "\n" in request.pattern or any(char in _REGEX_META for char in request.pattern):
            return None, "regex_query"
        if request.file_glob and not _SAFE_GLOB.fullmatch(request.file_glob):
            return None, "unsupported_glob"
        requested_path = Path(request.path)
        if not requested_path.is_absolute():
            requested_path = Path(request.cwd) / requested_path
        root = _canonical_git_root(requested_path)
        if root is None or root not in self.repo_roots:
            return None, "unindexed_repo_root"
        if time.monotonic() < self._fresh_until:
            return None, "post_write_freshness"
        if not self.binary.is_file() or not os.access(self.binary, os.X_OK):
            return None, "missing_binary"
        return root, None

    def _healthy_index(self, root: Path) -> tuple[Path | None, str | None]:
        index_dir = index_dir_for_root(root)
        receipt = index_dir / "root.json"
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            if Path(payload["root"]).resolve(strict=True) != root:
                return None, "index_root_mismatch"
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None, "missing_index"
        code, stdout, stderr, bounded = _run_bounded(
            [str(self.binary), "status", str(root), "--index-path", str(index_dir)],
            timeout=min(self.command_timeout_seconds, 2.0), max_stdout=32768, max_stderr=16384,
        )
        if bounded or code != 0 or stderr:
            return None, "unhealthy_server"
        status = stdout.decode("utf-8", errors="replace")
        required = ("Server status for ", "Watcher:    active", "Indexing:   complete", "Reconcile:  idle")
        if not all(item in status for item in required):
            return None, "stale_server"
        if "Reconcile pending: yes" in status or "Reconcile overdue: yes" in status or "Last reconcile error:" in status:
            return None, "stale_server"
        pid_match, port_match = _STATUS_PID.search(status), _STATUS_PORT.search(status)
        if not pid_match or not port_match or not _loopback_listener(int(pid_match.group(1)), int(port_match.group(1))):
            return None, "non_loopback_server"
        return index_dir, None

    def search(self, request):
        if SearchBackendDecline is None:
            return None
        root, reason = self._eligible(request)
        if reason:
            return SearchBackendDecline(reason)
        assert root is not None
        index_dir, reason = self._healthy_index(root)
        if reason:
            return SearchBackendDecline(reason)
        assert index_dir is not None
        argv = [
            str(self.binary), "--index-path", str(index_dir), "--line-number",
            "--no-heading", "--with-filename", "--color", "never", "-F",
        ]
        if request.output_mode == "files_only":
            argv.append("-l")
        if request.file_glob:
            argv.extend(["--glob", request.file_glob])
        argv.extend(["--", request.pattern, str(root)])
        max_rows = max(self.broad_match_threshold + 1, request.offset + request.limit + 1)
        code, stdout, stderr, bounded = _run_bounded(
            argv, timeout=self.command_timeout_seconds,
            max_stdout=min(8 * 1024 * 1024, max_rows * 4096), max_stderr=65536,
            max_lines=max_rows,
        )
        if bounded == "line_limit":
            return SearchBackendDecline("broad_result_volume")
        if bounded:
            return SearchBackendDecline(f"tgrep_{bounded}")
        if code not in {0, 1} or stderr:
            return SearchBackendDecline("tgrep_diagnostic")
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        if len(lines) > self.broad_match_threshold:
            return SearchBackendDecline("broad_result_volume")
        if request.output_mode == "files_only":
            files = tuple(str((root / line).resolve(strict=False)) if not os.path.isabs(line) else line for line in lines)
            return SearchBackendResult(
                files=files, total_count=len(files), backend="tgrep",
                route_reason="eligible_selective_literal",
            )
        matches = []
        for line in lines:
            parsed = _LINE.match(line)
            if not parsed:
                return SearchBackendDecline("incompatible_output")
            raw_path, line_number, content = parsed.groups()
            path = str((root / raw_path).resolve(strict=False)) if not os.path.isabs(raw_path) else raw_path
            matches.append(SearchBackendMatch(path, int(line_number), content))
        return SearchBackendResult(
            matches=tuple(matches), total_count=len(matches), backend="tgrep",
            route_reason="eligible_selective_literal",
        )
