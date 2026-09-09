# tgrep operator reference

## Artifact and compatibility

Pin and verify the official Microsoft tgrep artifact before installation. The HEL1 qualification used Linux x86_64 tgrep v1.0.5 with SHA-256 `1ef4125ab256586cd8008bfb4704bcaf12a40d24372d2c5ad548d22923432cf3`.

The plugin requires a Hermes core that exposes the generic profile-scoped `PluginContext.register_search_backend` seam. On an older core the plugin must fail to register without altering built-in `search_files`; rg remains available.

## Profile settings

Settings live under `plugins.entries.tgrep-code-search.settings` in the active profile's `config.yaml`.

- `enabled` (default `false`): master router switch.
- `binary` (default `~/.local/bin/tgrep`): executable path.
- `repo_roots` (default `[]`): explicit exact canonical Git top-level allowlist.
- `min_literal_length` (default `8`): lower bound for indexed literal routing.
- `max_limit` (default `100`): larger requested pages stay native.
- `broad_match_threshold` (default `200`): tgrep aborts and falls back when initial volume is broad.
- `freshness_quarantine_seconds` (default `2.0`): guaranteed native interval after a successful write/patch/terminal call.
- `command_timeout_seconds` (default `5.0`): status and search deadline.

The plugin supports only local content searches, context `0`, output modes `content`/`files_only`, plain literals, and a conservative single positive glob. Everything else declines to native search.

## Index and service lifecycle

Indexes resolve to:

```text
<HERMES_HOME>/plugin-data/tgrep-code-search/indexes/<sha256(canonical-root)[:24]>/
```

The lifecycle script refuses a subdirectory, non-Git directory, missing binary, or malformed profile name.

```bash
python3 scripts/tgrep_lifecycle.py prepare \
  --profile default --hermes-home ~/.hermes \
  --root /absolute/exact/git/root

python3 scripts/tgrep_lifecycle.py start \
  --profile default --hermes-home ~/.hermes \
  --root /absolute/exact/git/root

python3 scripts/tgrep_lifecycle.py status \
  --profile default --hermes-home ~/.hermes \
  --root /absolute/exact/git/root

python3 scripts/tgrep_lifecycle.py stop --profile default
```

`start` installs a user-level `hermes-tgrep@.service`, writes a profile-specific environment file, and enables only the named instance. `stop` leaves indexes and user data intact.

Run separate instances for `default` and `hermesdev`; their env files and index paths must differ even when the indexed root is the same.

## Eligibility and health

Before every indexed query the plugin checks:

1. local environment and supported query semantics;
2. exact canonical root equals an allowlisted Git top-level;
3. profile-local `root.json` exactly matches root and index;
4. tgrep status succeeds with watcher active, indexing complete, reconciliation idle/pending no/overdue no, and a successful reconciliation timestamp;
5. status PID is alive and its port is listening only on loopback;
6. no freshness barrier is active.

A status diagnostic or any stderr from the search is degraded evidence and triggers rg fallback. This includes tgrep v1.0.5's misleading `Server unreachable` prefix on invalid regex; regex never reaches tgrep through this router.

## Routing reasons

Successful indexed responses expose:

```text
backend: tgrep
route_reason: eligible_selective_literal
```

Native fallback exposes `backend: rg` (or `grep`) and one reason such as:

- `disabled`, `remote_environment`, `regex_query`, `short_literal`;
- `unsupported_context`, `unsupported_output_mode`, `unsupported_glob`, `high_limit`;
- `unindexed_repo_root`, `missing_binary`, `missing_index_metadata`, `index_metadata_mismatch`;
- `post_write_freshness`, `unhealthy_server`, `non_loopback_server`;
- `tgrep_timeout`, `tgrep_diagnostic`, `tgrep_error`, `broad_result_volume`, `incompatible_output`;
- `backend_error:tgrep` or `backend_invalid:tgrep` from the core safety seam.

## Freshness

Watcher readiness does not guarantee immediate post-write visibility. The `post_tool_call` hook marks all configured roots stale after successful `write_file`, `patch`, or `terminal` execution. Searches during the bounded quarantine use rg. This is deliberately conservative for terminal commands whose mutation surface cannot be proven from the command string.

Create/modify/delete tests must assert the first subsequent search uses rg and sees the current filesystem. After the barrier, require a fresh status receipt before allowing tgrep again.

## Metrics and acceptance

Use at least 15 warm repetitions after one warm-up. Record median and p95 for the same query/corpus and compare sorted paths, line numbers, text, and exit semantics with rg.

Promotion gate:

- at least 2× on representative selective queries;
- at least 25 ms median absolute saving unless a different bound is justified by measured agent latency;
- parity for selective and no-match cases;
- broad, regex, unsupported, missing, unhealthy, diagnostic, and immediate-write cases visibly route to rg;
- 12 concurrent indexed queries pass;
- index disk and server RSS fit the host budget;
- listener is loopback-only and no `.tgrep`/index exists inside the repo.

## Rollback and cleanup

1. Set plugin `settings.enabled: false` or remove the plugin from that profile's enabled list.
2. Restart/reload through the existing Hermes runtime owner if required to unload plugin registration.
3. Stop only `hermes-tgrep@<profile>.service` for the affected profile.
4. Verify `search_files` returns native rg results and gateway health is unchanged.
5. Preserve indexes and user/shared data unless deletion is separately authorized.
