---
name: tgrep-for-hermes
description: "Use when operating the optional tgrep backend for Hermes code search."
version: 0.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-search, tgrep, ripgrep, indexing, plugin]
    related_skills: [hermes-agent]
---

# tgrep for Hermes

Operate tgrep as an **optional profile-scoped backend** behind Hermes `search_files`. The plugin requires the generic `register_search_backend` core seam; it does not override the built-in tool. Hermes keeps root validation, blocked-path filtering, redaction, pagination shaping, and native rg/grep fallback.

## Routing contract

Use tgrep only when every gate passes:

- plugin enabled for the active profile;
- local environment and `target=content`;
- exact canonical Git top-level is explicitly allowlisted and indexed;
- pattern is a selective literal/symbol with no regex metacharacters;
- output mode is `content` or `files_only`, context is zero, and any glob is allowlisted;
- binary, root metadata, server PID, loopback listener, watcher, indexing, and reconciliation are healthy;
- no immediate post-write freshness barrier is active.

Use native rg/grep for broad/high-volume queries, regex, single files, subdirectories, hidden/ignored/binary/encoding semantics, unsupported flags/modes, remote backends, missing/unhealthy/stale tgrep, diagnostics, incompatible output, and immediate post-write truth.

## Profile isolation

Keep settings, metadata, indexes, and process ownership separate for every `HERMES_HOME`:

- default: `~/.hermes/plugin-data/tgrep-code-search/`
- named profile: `~/.hermes/profiles/<name>/plugin-data/tgrep-code-search/`

Install the plugin package independently under each profile's `plugins/` directory. Sharing immutable source bytes is acceptable; sharing config, index, PID, status, or mutation state is not. Never place `.tgrep` or an index inside a repository.

## Lifecycle

1. Verify the exact tgrep binary/version/hash and the exact Git top-level.
2. Prepare the profile-local index with `scripts/tgrep_lifecycle.py prepare`.
3. Start the profile instance through the existing `systemd --user` owner with `scripts/tgrep_lifecycle.py start`.
4. Require `Watcher: active`, `Indexing: complete`, `Reconcile: idle`, pending `no`, overdue `no`, and a loopback-only listener before routing.
5. Read `backend` and `route_reason` in `search_files` output to diagnose every route.
6. On rollback, disable the plugin setting and stop only the named profile service. Do not delete indexes or shared/user data.

See [operator reference](references/operator.md) for exact commands, configuration, diagnostics, metrics, and cleanup.

## Freshness rule

A watcher is asynchronous. Successful `write_file`, `patch`, or `terminal` execution activates a bounded freshness barrier for configured roots. Searches during the barrier use native rg. This guarantees immediate post-write truth does not depend on watcher timing. Re-enable tgrep only after the barrier and a fresh healthy status receipt.

## Failure behavior

- A backend decline is normal and must fall through to native search.
- Backend exceptions, malformed/out-of-root results, non-zero search exits, stderr diagnostics, timeouts, output caps, and tgrep v1.0.5's misleading `Server unreachable` message all fall back to native search.
- tgrep is never a mandatory dependency. If the plugin cannot load or tgrep is absent, built-in `search_files` remains available.

## Verification checklist

- selective literal → `backend=tgrep` and parity with rg;
- broad query, regex, unsupported mode → `backend=rg` with exact reason;
- missing binary/index, unhealthy server, stale barrier, diagnostics → rg;
- create/modify/delete followed immediately by search → current filesystem truth via rg;
- default and named profile use different index paths and service instances;
- 12 concurrent selective searches return parity;
- server listener is loopback only;
- no `.tgrep` or index exists inside the repository;
- disabling plugin + stopping the exact profile instance restores rg-only behavior.

## Done criteria

Report exact core/plugin SHAs, tgrep artifact hash, profile configs, index/status/PID/listener receipts, selective/broad/failure/freshness/concurrency E2E, rg parity, median+p95 latency, gateway health after owner-managed restart, public CI, and rollback proof.
