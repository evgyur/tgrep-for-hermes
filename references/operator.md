# tgrep operator reference

## Tested artifact

The initial Hermes evaluation pinned Microsoft `tgrep` v1.0.5 for Linux x86_64 musl and verified the release-provided SHA-256 before installing the binary. Re-check the current official GitHub release and checksum before every upgrade; do not treat this historical pin as an update instruction.

Canonical upstream: <https://github.com/microsoft/tgrep>

## Commands

Use an index outside the repository:

```bash
TGREP="$HOME/.local/bin/tgrep"
ROOT="/absolute/repository"
IDX="$HOME/.cache/tgrep/indexes/<repo-key>"

"$TGREP" index "$ROOT" --index-path "$IDX"
"$TGREP" serve "$ROOT" --index-path "$IDX"
"$TGREP" status "$ROOT" --index-path "$IDX"
"$TGREP" --index-path "$IDX" -F -- "ExactSymbol" "$ROOT"
"$TGREP" --index-path "$IDX" --no-index -F -- "ExactSymbol" "$ROOT"
```

Keep all flags before `--`; place the pattern and explicit root after it. `index`, `serve`, `status`, `count-files`, `search`, and `help` are subcommand-like tokens, so `--` prevents a pattern from being misparsed.

## Benchmark acceptance

Use at least 15 warm repetitions per query after one untimed warm-up. Record median and p95 wall latency. Compare sorted line output and exit codes with ripgrep. A practical promotion gate is:

- at least 2x on representative selective queries;
- at least 25 ms median absolute savings per agent search;
- output and exit-code parity across the fixed corpus;
- freshness canary passes;
- server RSS and index disk fit the host budget;
- broad queries retain native fallback.

Adjust the absolute threshold only with observed end-to-end agent latency evidence.

## Known caveats

- Linux gives smaller gains than macOS/Windows because warm ripgrep scans are already fast.
- High-match-volume queries may be much slower due to indexed server serialization and delivery.
- `--hidden`, unrestricted/no-ignore, binary/text/encoding modes, `--no-index`, and single-file paths may bypass the index.
- `-L`, `--one-file-system`, and `--ignore-file` only affect full scans; do not assume indexed searches honor them.
- On-disk-only indexes do not update after edits.
- Watcher updates are asynchronous. Native mode can miss events until reconciliation; polling has bounded cadence rather than immediate freshness.
- A server on an existing index may report indexing complete while startup reconciliation/watch registration is still in progress.
- Invalid regex currently returns exit `2`, but v1.0.5 can prepend a misleading `Server unreachable, falling back to local index` warning even when the server remains healthy. Preserve stderr and classify this as degraded diagnostics, not a server crash.
- `--json` mostly matches ripgrep, but invalid UTF-8 line bytes are replacement text rather than ripgrep-style base64.

## Hermes integration boundary

A user-local skill changes agent procedure, not the implementation of Hermes `search_files`. Do not claim tgrep accelerates that built-in tool unless a separately reviewed integration routes it explicitly. Prefer a least-privilege plugin/tool wrapper over core edits if future end-to-end evidence justifies integration: canonicalize the root, allowlist flags, keep loopback-only serving, return stdout+stderr+exit code, and preserve native fallback.
