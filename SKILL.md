---
name: tgrep-for-hermes
description: "Use when operating tgrep for Hermes code search."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-search, tgrep, ripgrep, benchmark, indexing]
    related_skills: [hermes-agent, agent-capability-evaluation]
---

# tgrep for Hermes

Use `tgrep` as a **specialized indexed search path**, not a blanket replacement for Hermes `search_files`/ripgrep.

## Decision rule

Promote tgrep for a repository only after a same-corpus benchmark shows a useful absolute latency win on selective symbol/literal searches. Keep the native search path when:

- the repository is small or unindexed;
- the query is broad/high-volume;
- the newest filesystem state is mandatory;
- hidden, ignored, encoded, binary, archive, or single-file behavior is required;
- a requested flag forces a scan or lacks indexed equivalence.

A speedup ratio without meaningful milliseconds saved is not enough. Account for index disk, server RSS, build time, watcher health, and operational ownership.

## Safe workflow

1. Verify the exact binary, version, repository root, free disk/RAM, and whether the repository is Git-backed.
2. Establish the native baseline on the same fixed query corpus: selective literal, realistic regex, broad/high-match, no-match, invalid regex, and bounded concurrency.
3. Build the index outside the repository, under a private cache path. Keep index/search/serve flags aligned.
4. Start `serve` only for an approved bounded repository. Wait until status reports `Indexing: complete`, watcher active, and reconciliation idle.
5. Compare exit code and normalized output with ripgrep; measure repeated median and p95 latency.
6. Test create/modify/delete freshness. Use the native path or `tgrep --no-index` when a just-written file must be visible immediately.
7. Stop experiment servers and remove obsolete evaluation indexes. Never commit `.tgrep/`.

See [operator reference](references/operator.md) for commands, thresholds, caveats, and the pinned tested release.

## Search routing

- Prefer fixed-string searches for symbols and user-provided literals.
- Narrow by type/glob and request filenames first when output could be large.
- Route broad/high-volume terms to Hermes `search_files`/ripgrep; indexed result delivery can be dramatically slower.
- Exit `0` means matches, `1` means no matches, and `2` means error.
- Always inspect stderr. An indexed warning or fallback changes the evidence even if stdout looks correct.
- Do not forward arbitrary model-generated flags or paths through a wrapper. Canonicalize roots beneath the assigned repository and allowlist search-only flags.

## Hard boundaries

- An on-disk index is a snapshot, not live truth.
- A running watcher is asynchronous; a search immediately after a write can race it.
- `status` reporting `Indexing: complete` alone does not prove watcher readiness or current reconciliation.
- Do not expose a repository-wide tgrep server beyond loopback.
- Do not modify Hermes core or replace `search_files` merely because the CLI is installed.

## Output Contract

Report: exact tgrep version/artifact, corpus file/byte count, index build time/size/peak memory, server RSS/watcher state, per-query median+p95 for native vs tgrep, correctness/freshness/error results, role verdict, fallback, and residual risks.

## Quick Test Checklist

- Positive: selective literal returns the same lines/exit code as ripgrep and is materially faster.
- Negative: broad high-match query remains on the native route.
- Freshness: create, modify, and delete are observed; immediate-truth work uses native or `--no-index`.
- Failure: invalid regex exits `2` and stderr is retained.
- Persistence: root and linked reference validate and the skill reloads through `skill_view`.

## Done criteria

The binary and index are verified, baseline and candidate used the same corpus, outputs match, freshness and errors were exercised, server/index resource costs are known, routing is specialized rather than global, and cleanup/readback is complete.
