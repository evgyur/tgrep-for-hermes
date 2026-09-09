# tgrep for Hermes

An optional, profile-scoped [Microsoft tgrep](https://github.com/microsoft/tgrep) backend for Hermes `search_files`, plus its operating skill.

The plugin is deliberately hybrid. Selective literal/symbol queries can use the indexed tgrep server; everything broad, regex-based, unsupported, freshness-sensitive, unhealthy, or ambiguous stays on Hermes' native ripgrep path.

## Safety architecture

- The plugin registers through Hermes' generic `register_search_backend` seam; it does **not** override `search_files`.
- Hermes retains path validation, blocked-path filtering, redaction, pagination output shaping, and native fallback.
- tgrep is optional. Missing plugin, binary, index, or server leaves rg working.
- Only explicitly configured exact Git top-levels are eligible.
- Every profile has separate settings, indexes, metadata, server instance, and mutation barrier.
- Indexes live under profile-owned plugin data, never in a repository.
- tgrep v1.0.5 binds its server to `127.0.0.1:0`; the plugin independently verifies the listening socket is loopback.

## Measured baseline

Ubuntu Linux x86_64, tgrep v1.0.5, warm client/server searches. Normalized output and exit codes matched.

| Corpus / query | ripgrep median / p95 | tgrep median / p95 | Outcome |
|---|---:|---:|---:|
| 6,120 files — selective literal | 27.1 / 28.6 ms | 11.2 / 12.9 ms | 2.42× faster |
| 6,120 files — second selective literal | 26.3 / 27.9 ms | 7.7 / 8.6 ms | 3.40× faster |
| 6,120 files — realistic regex | 27.3 / 29.0 ms | 43.7 / 46.5 ms | rg retained |
| 6,120 files — broad, 51,982 lines | 35.4 / 38.2 ms | 842.8 / 882.3 ms | rg retained |
| 14,374 files — selective literal | 52.8 / 55.4 ms | 11.8 / 13.4 ms | 4.48× faster |
| 14,374 files — no match | 52.0 / 55.2 ms | 4.0 / 4.7 ms | 13.09× faster |
| 14,374 files — broad, 84,097 lines | 90.3 / 117.5 ms | 1,512.6 / 1,688.3 ms | rg retained |

Indexes cost 96.2/189.1 MB; build time was 1.61/3.90 s; larger-corpus server RSS was about 187 MB. Watcher create/modify/delete and 12 concurrent queries passed in the original evaluation.

## Requirements

- Hermes revision exposing `PluginContext.register_search_backend`.
- Microsoft tgrep installed separately; this repository does not vendor binaries.
- Linux for the current loopback `/proc` listener verification.
- `systemd --user` for the supplied lifecycle owner.

## Install per profile

Place an immutable checkout/copy in each selected profile's `plugins/tgrep-code-search` directory, then enable `tgrep-code-search` in that profile and configure its settings. No `tools.override` grant is required.

```yaml
plugins:
  enabled: [tgrep-code-search]
  entries:
    tgrep-code-search:
      settings:
        enabled: true
        binary: ~/.local/bin/tgrep
        repo_roots:
          - /absolute/exact/git/root
        min_literal_length: 8
        max_limit: 100
        broad_match_threshold: 200
        freshness_quarantine_seconds: 2.0
        command_timeout_seconds: 5.0
```

Prepare and start one profile-owned server:

```bash
python3 scripts/tgrep_lifecycle.py start \
  --profile default \
  --hermes-home ~/.hermes \
  --root /absolute/exact/git/root
```

Run the equivalent command with the named profile's own `HERMES_HOME`; never reuse the default index path.

## Contents

- `plugin.yaml`, `__init__.py`, `tgrep_backend.py` — native backend plugin.
- `SKILL.md` — routing and operating contract.
- `references/operator.md` — lifecycle, fallback, diagnostics, metrics, rollback.
- `scripts/tgrep_lifecycle.py` — exact-root index and profile service manager.
- `scripts/validate.py`, `scripts/test_contract.py` — deterministic packaging checks.
- `tests/` — router, lifecycle, safety, and public hygiene tests.

## License

MIT
