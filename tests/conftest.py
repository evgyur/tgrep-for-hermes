"""Small public-CI stub; real Hermes integration is covered in the core repository tests."""

import sys
import types
from dataclasses import dataclass, field

try:
    import hermes_cli.search_backends  # noqa: F401
except ImportError:
    package = sys.modules.setdefault("hermes_cli", types.ModuleType("hermes_cli"))
    module = types.ModuleType("hermes_cli.search_backends")

    @dataclass(frozen=True)
    class SearchBackendRequest:
        pattern: str
        path: str
        file_glob: str | None
        limit: int
        offset: int
        output_mode: str
        context: int
        environment_kind: str
        is_local: bool
        cwd: str

    @dataclass(frozen=True)
    class SearchBackendMatch:
        path: str
        line_number: int
        content: str

    @dataclass
    class SearchBackendResult:
        backend: str
        route_reason: str
        matches: list = field(default_factory=list)
        files: list = field(default_factory=list)
        counts: dict = field(default_factory=dict)
        total_count: int = 0
        truncated: bool = False
        limit_reason: str | None = None
        warning: str | None = None

    @dataclass(frozen=True)
    class SearchBackendDecline:
        route_reason: str

    module.SearchBackendRequest = SearchBackendRequest
    module.SearchBackendMatch = SearchBackendMatch
    module.SearchBackendResult = SearchBackendResult
    module.SearchBackendDecline = SearchBackendDecline
    package.search_backends = module
    sys.modules["hermes_cli.search_backends"] = module
