# reproduce/

One script per published figure and table. Each reads only committed artifacts, needs no GPU, no
cluster and no downloads, and runs in seconds to a couple of minutes.

```bash
pip install -e ".[figures]"
for s in reproduce/*.py; do python "$s"; done
```

Outputs land in `build/figures/`. Every script prints its numbers to stdout as well as drawing,
so you can check a value without a plotting stack — and each skips the plot rather than failing
if matplotlib is absent.

| script | exhibit | headline it regenerates |
|---|---|---|
| `fig1_reaction_budget.py` | Figure 1 | 2.82× median at R=100, 31/32 comparable, 0 losses |
| `fig2_floor_and_ceiling.py` | Figure 2 | flow ordering vs random/reverse; 0.946 of achievable gain |
| `fig3_selection_vs_enumeration.py` | Figure 3 | 2.51× against the competing planner on a shared pool |
| `table1_external.py` | Table 1 | 1.41× mean, 1.26× worst seed, against its strongest arm |
| `figA1_yield_risk.py` | Appendix A1 | step yield is 0.73–0.77 for **both** arms — length, not chemistry |
| `figA2_two_knob_surface.py` | Appendix A2 | 397/400 comparable cells cheaper, 0 losses |

`docs/CLAIMS.md` maps each of these to the claim it supports **and what would falsify it**.

---

## This is the reviewer's door

It is deliberately not extensible. These scripts are frozen against committed artifacts so that
"the numbers in the paper come from the code in this repository" is a checkable statement rather
than an assurance — `fig1_reaction_budget.py` runs in CI for exactly that reason.

If you want to run the method on **your own** data, you want the other door:
`docs/INPUT_CONTRACT.md` and `notebooks/`. Nothing here will help with that.

## Reading the output honestly

Three conventions are applied throughout, and each exists because the loose version flatters a
result:

**Comparable cells only.** A median is taken over cells where *both* arms were budget-binding —
qualifying candidates remained and the next one did not fit. An arm that ran out of material did
not choose to stop, so quoting it as "N molecules at R reactions" would imply it could have
spent the budget and declined.

**Never interpolated.** "Molecules at R" is the cumulative count at the last point whose
cumulative reactions do not exceed R.

**Lead with the smaller margin.** Where a comparison can be made against several of a
competitor's configurations, the number quoted is against its *strongest*. Where a threshold
admits two defensible values, both arms are reported at each and the smaller ratio leads.

Several scripts also report figures that cut against the method — `figA1` shows hub-batching's
mean route yield is *lower* on sEH, and Figure 3's excluded seed **lowered** the λ=0 ratio from
4.71× to 3.26×. Those are not oversights.

## Data currency

Everything under `artifacts/` is generation `v1`, and a clean re-run is under way in the
research tree. 27 files are marked `invalidated` (every 6TD3 cell — that reward was replaced,
so there is no newer measurement of the same quantity) and 2 are `v1-stale`. See
`artifacts/README.md`; `fig1_reaction_budget.py` already excludes 6TD3 from its headline and
reports it separately under `--include-uncalibrated`.
