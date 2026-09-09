import importlib.util
from pathlib import Path


class FakeContext:
    def __init__(self):
        self.backends = []
        self.hooks = []

    def get_config(self, _key, default=None):
        return default

    def register_search_backend(self, name, callback):
        self.backends.append((name, callback))

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))


def test_native_plugin_entrypoint_registers_backend_and_freshness_hook():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "hermes_ext_tgrep", root / "__init__.py", submodule_search_locations=[str(root)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = FakeContext()
    module.register(ctx)
    assert [name for name, _ in ctx.backends] == ["tgrep"]
    assert [name for name, _ in ctx.hooks] == ["post_tool_call"]


def test_entrypoint_is_inert_without_core_search_backend_seam():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "hermes_ext_tgrep_legacy", root / "__init__.py", submodule_search_locations=[str(root)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.register(object())
