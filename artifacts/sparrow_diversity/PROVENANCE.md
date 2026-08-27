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

## `ours_r100.csv` — our own arm

**Harvested from run directories, verified against the log.** Every value here comes
from a campaign `summary.json`, and every one reproduces Logs/062 Result 12 exactly:
seed 42 -> 82, seed 43 -> 81, seed 44 -> 82.

Seeds 43 and 44 were re-derived on 2026-08-27 because their original campaign outputs
were not where any harvest could read them. Nothing was re-trained and nothing was
re-sampled: training, sampling and enumeration for those cells were already complete
(`RETRAIN_RUNBOOK` marks them "do not re-train"), so only the final selection stage was
re-run, against the surviving artifacts at `t45_seh_seed43/` and `t45_seh_seed44/`.
Minutes of CPU. That the re-run reproduced the log's numbers to the unit is the check
that it used the right inputs.

Configuration, which had to be matched rather than guessed: gate 7.0, tau 0.5,
`free_frag` child policy, `prebuild_k=0`, and the promoted-fragment snapshot
`fragments_4000.json` — chosen because its 1,600 `chosen_smiles` match the
`n_promoted_fragments: 1600` the sampling stage recorded. A different snapshot would
price the same library differently.

**A near-miss worth recording.** Other campaign outputs for these seeds *do* survive
at gate 7.0 (`seed_curves/m16_seed4{3,4}_scentseh_thr7_k0`, giving 79 and 83) and are
NOT substitutes: they were run against the `matrix16` enumeration, whereas both arms of
this comparison were computed on the `t45` enumeration. Substituting them would leave
the two arms selecting from different candidate pools — the exact confound that got
Results 13-15 withdrawn, where both runs reported `Optimal` and the only tell was an
mtime nothing checked.

Every pick in our arm is a distinct molecule by construction — the greedy accepts a
child only if it clears the gate *and* is Tanimoto-far from everything already taken —
so `n_selected` and `n_modes_kept` are necessarily equal. That is not a coincidence to
be explained away; it is the difference the figure is about.

**One caveat on seed 44:** its full run reaches 270 modes rather than 300 (pool-limited
at gate 7.0). This does not touch the readout used here, because the 100-reaction budget
binds long before the pool is exhausted.
