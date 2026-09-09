"""Hermes entry point for the optional tgrep content-search backend."""

try:
    from .tgrep_backend import TgrepBackend
except ImportError:  # direct-source test/import mode
    from tgrep_backend import TgrepBackend


def register(ctx):
    # Older Hermes revisions do not expose the optional seam. Stay inert so
    # native rg remains fully operational across rollback or mixed rollout.
    if not hasattr(ctx, "register_search_backend"):
        return
    backend = TgrepBackend.from_context(ctx)
    ctx.register_search_backend("tgrep", backend.search)
    ctx.register_hook("post_tool_call", backend.observe_tool_call)
