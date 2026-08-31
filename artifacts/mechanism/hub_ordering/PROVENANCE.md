# Floor panel — what it was measured on

| | |
|---|---|
| model | SCENT |
| oracle | sEH surrogate proxy (not docking) |
| checkpoint | one frozen training run, 1,600 promoted fragments |
| enumeration | 200 hubs, `campaign_enum_seh_70363` |
| gate / tau | reward > 7.0 / Tanimoto < 0.5 |
| selection | free_frag child policy, prebuild_k=20, rank_by=build_score |
| replicates | **one cell, one seed** |

**This is NOT the checkpoint the matrix cells use.** Figure 1's `scent_seh`
comes from the `scent_seh_5k/seed42` series; this ablation predates it and
uses a separate SCENT sEH training run. The two happen to land on similar
numbers at gate 7.0, which is a coincidence of two checkpoints and not a
cross-validation -- do not present it as one.

What makes the ablation valid is narrower and sufficient: all arms share
ONE checkpoint and ONE enumeration, so the only thing that varies is the
walk order. Scope differs from the ceiling panel, which spans 14 cells
across four generators and four oracles.
