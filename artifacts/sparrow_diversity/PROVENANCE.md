# Table 2 — selection vs enumeration under SPARROW's own diversity mechanism

Harvested from the cluster run tree by `tools/harvest/sparrow_diversity.py`; the
source tree was 572 MB of MILP solutions, of which these 64 KB are the part any
figure or table needs. `provenance.json` records the md5 and mtime of every source
file, because this comparison has already been broken once by an input changing
underneath it (see *the frozen-inputs lesson* below).

## Files

| file | contents |
|---|---|
| `r100.csv` | 50 rows at the primary 100-reaction budget |
| `frontier_all.csv` | 308 rows, every budget from 50 to 1200 |
| `provenance.json` | per-source md5, mtime, size; skipped smoke/debug dirs |

Column notes:

- `n_modes_kept` is **distinct molecules** — the count the claim is about. `n_selected`
  is what the optimizer bought, which is a different and much larger number.
- `mean_pairwise_sim` is over the whole selection; `mean_pairwise_sim_kept` is over
  the survivors only. Logs/062's tables quote the former as "meanSim".
- `milp_status` and `solve_s` are load-bearing, not diagnostics. A `TimeLimit` row is
  a **lower bound on the competitor**, so it flatters us and cannot be quoted as a
  ratio. `seed_inferred=True` marks rows whose seed came from the tag grammar rather
  than an explicit suffix (the unsuffixed runs are seed 42, confirmed against
  Logs/062 Result 12).

## Which numbers stand, and which do not

Logs/062 was revised four times and its sections are **not** in chronological order —
the `Update 2026-08-20` block sits *after* the `Update 2026-08-23` block in the file.
Read by date, not by position. The latest statement governs.

| number | status | basis |
|---|---|---|
| **2.51×** distinct at R=100 vs BC-Enum-SB | ✅ **quotable** | Result 12, within-seed on seeds 43 and 44 (2.45× and 2.56×). Affirmed as unaffected by the 2026-08-23 update: *"different arm"* |
| **λ=0 → 98 selected, 2 distinct** | ✅ **quotable** | Result 6, inside Results 1–12, which the withdrawal explicitly leaves standing |
| λ=1 lifts BC-Enum-SB 24→33 (s43), 26→32 (s44) | ✅ quotable | Result 11 |
| **2.27×** "selection alone, identical candidates" | ⛔ **WITHDRAWN** | Result 15. The 2026-08-23 update — the file's most recent — says *"Results 13-15 stay withdrawn"*, because HB-Enum-SB does not converge on the corrected 123k–150k pools and the arm can only be reported as a **bound** |
| 1.67× (same claim, n=1) | ⛔ withdrawn | Result 14, superseded by 15 and withdrawn with it |
| 3.4× (82 vs 24) | ⚠️ superseded | Result 6's seed-42 pairing; its competitor row is `TimeLimit`, i.e. a lower bound. Result 12 replaces it with 2.51× |

**Seed 42 is excluded from the headline ratio on purpose.** Its competitor row hit
the solver's time limit, so its 3.42× is a lower bound rather than a measurement.
Excluding it *lowers* the number we quote.

## The frozen-inputs lesson

Results 13–15 were originally measured on **mixed enumerations**: a per-hub cap fix
rewrote the candidate pools (21k → 120k–152k above gate) after one arm had read the
old files and before the other read the new ones. Both runs completed, both reported
`Optimal`, and both produced plausible libraries. The only tell was an input mtime,
which nothing checked.

That is why `provenance.json` exists, and why a comparison claiming "the same
candidates" must read from a frozen snapshot rather than a shared scratch tree that
other jobs are still writing.

## `ours_r100.csv` — our own arm, and how it got here

The competitor rows are harvested from run artifacts. Our three seed values are
**transcribed from Logs/062 Result 12**, not re-derived, because the seed-43/44
campaign summaries behind them are not in a location this harvest can read. That entry
is affirmed standing by the log's own 2026-08-23 update, and the seed-42 value (82)
independently matches `artifacts/external/head_to_head_r100.csv`, which *is* harvested
from a run directory — so the one value that can be cross-checked, checks.

**To make this fully self-sourcing**, re-run the seed-43/44 gate-7.0 campaigns and
harvest their `summary.json` the way `tools/harvest/external.py` does. Until then this
file is the one place in `artifacts/` whose numbers come from a document rather than
from a run, and it is labelled as such in its own `source` column.

Every pick in our arm is a distinct molecule by construction — the greedy accepts a
child only if it clears the gate *and* is Tanimoto-far from everything already taken —
so `n_selected` and `n_modes_kept` are necessarily equal. That is not a coincidence to
be explained away; it is the difference the figure is about.
