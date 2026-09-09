# tgrep for Hermes

A small Hermes skill for deciding **when indexed code search is actually worth it**.

It treats [Microsoft tgrep](https://github.com/microsoft/tgrep) as a specialized path for repeated selective searches in larger repositories—not as a blanket replacement for Hermes `search_files` or ripgrep.

## Measured results

Ubuntu Linux x86_64, `tgrep` v1.0.5, warm client/server searches. Every row used the same corpus and query for ripgrep and tgrep; normalized output and exit codes matched.

| Corpus / query | ripgrep median / p95 | tgrep median / p95 | Outcome |
|---|---:|---:|---:|
| 6,120 files — selective literal | 27.1 / 28.6 ms | 11.2 / 12.9 ms | 2.42× faster |
| 6,120 files — second selective literal | 26.3 / 27.9 ms | 7.7 / 8.6 ms | 3.40× faster |
| 6,120 files — realistic regex | 27.3 / 29.0 ms | 43.7 / 46.5 ms | tgrep slower |
| 6,120 files — broad, 51,982 lines | 35.4 / 38.2 ms | 842.8 / 882.3 ms | tgrep ~24× slower |
| 14,374 files — selective literal | 52.8 / 55.4 ms | 11.8 / 13.4 ms | 4.48× faster |
| 14,374 files — no match | 52.0 / 55.2 ms | 4.0 / 4.7 ms | 13.09× faster |
| 14,374 files — realistic regex | 52.9 / 55.2 ms | 49.4 / 63.3 ms | near tie |
| 14,374 files — broad, 84,097 lines | 90.3 / 117.5 ms | 1,512.6 / 1,688.3 ms | tgrep ~16.7× slower |

### Resource cost

| Corpus | Index build | Index size | Peak/server memory |
|---|---:|---:|---:|
| 6,120 files | 1.61 s | 96.2 MB | ~111 MB build peak RSS |
| 14,374 files | 3.90 s | 189.1 MB | ~187 MB server RSS |

The watcher passed create → modify → delete freshness checks, and 12 concurrent selective searches returned identical successful output.

## Verdict

Use tgrep when all of these are true:

- the repository is large enough that selective ripgrep scans are material;
- the workload performs repeated symbol or fixed-string searches;
- the measured absolute saving is useful (the skill defaults to 25 ms);
- index disk and server memory fit the host budget.

Keep ripgrep/Hermes native search for broad queries, immediate post-write truth, and modes that bypass or weaken indexed semantics.

## Install the skill

```bash
git clone https://github.com/evgyur/tgrep-for-hermes.git ~/.hermes/skills/tgrep-for-hermes
python3 ~/.hermes/skills/tgrep-for-hermes/scripts/validate.py
```

Install `tgrep` separately from its [official upstream](https://github.com/microsoft/tgrep). This repository does not vendor binaries.

## Contents

- `SKILL.md` — trigger, routing policy, safety boundaries, and done criteria.
- `references/operator.md` — commands, benchmark gate, integration caveats.
- `scripts/validate.py` — deterministic contract validation.
- `scripts/test_contract.py` — positive plus negative contract test.

## Important limitation

Installing a skill changes agent procedure; it does **not** replace or accelerate Hermes `search_files`. A future native/plugin integration needs separate path confinement, flag allowlisting, fallback, and end-to-end benchmarks.

## License

MIT
