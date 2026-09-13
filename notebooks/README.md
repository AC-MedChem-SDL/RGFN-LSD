# Notebooks

Worked examples, one per extension point. All CPU, all on the bundled toy dataset, all run in
seconds.

```bash
pip install -e ".[notebooks]"
jupyter lab notebooks/
```

| | | needs |
|---|---|---|
| [`01_quickstart`](01_quickstart.ipynb) | run both strategies, read the budget answer, plot the curve | CPU |
| [`02_bring_your_own_strategy`](02_bring_your_own_strategy.ipynb) | write a hub-selection strategy and test whether it helped | CPU |
| [`03_bring_your_own_generator`](03_bring_your_own_generator.ipynb) | write the file contract from any environment | CPU |
| [`04_bring_your_own_reward`](04_bring_your_own_reward.ipynb) | swap the oracle, calibrate a gate, see the library move | CPU |
| [`05_bring_your_own_chemistry`](05_bring_your_own_chemistry.ipynb) | your building blocks, your reaction templates | CPU |
| [`06_export_a_bench_plan`](06_export_a_bench_plan.ipynb) | buy lists, protocols, reaction schemes — the deliverable | CPU |
| [`07_your_own_trained_model`](07_your_own_trained_model.ipynb) | drive a real checkpoint: sample, recover flow, enumerate | **torch + a checkpoint** |

Start with `01`. The rest are independent of each other.

`07` is the only one with heavy requirements, and it **skips cleanly** if you have no
checkpoint — so you can read it through before deciding whether the install is worth it.
`pip install -e ".[generators]"` then `python3 setup/fetch_models.py --list`.

---

## The numbers in here are not results

Every notebook runs on `examples/toy/` — 432 molecules whose structures, reactions and routes
are **real** (RDKit fired every template), but whose *reward* is RDKit's QED standing in for a
target-specific oracle, and whose policy log-probabilities were generated from a self-consistent
model of a trained GFlowNet rather than recovered from one.

That is deliberate. A tutorial should run everywhere in seconds without a download, and it
should never be mistakable for a published result. `examples/toy/meta.json` carries the same
caveat, so a file opened in isolation still says so.

**For the paper's numbers, run [`reproduce/`](../reproduce/)** — one script per figure and
table, reading committed artifacts, no accelerator.

---

## They are generated, not hand-edited

The source is `tools/notebook_specs/*.py`; `tools/build_notebooks.py` renders them.

```bash
python3 tools/build_notebooks.py           # rebuild
python3 tools/build_notebooks.py --check   # fail if a committed notebook is stale
```

Three reasons, all of which bite eventually:

- **Diffs.** A hand-edited notebook diffs as one enormous JSON line; a spec diffs as prose.
- **Outputs.** Generated notebooks are born with no stored outputs, no execution counts and no
  kernel metadata — so they stay small and carry no username or interpreter path into a tree the
  anonymity gate then has to scrub.
- **Drift.** When an API changes, the fix is one edit to a spec rather than a hunt through JSON.

If you edit a `.ipynb` directly, move the change into its spec before committing — otherwise the
next regeneration silently reverts you. `tests/test_notebooks.py` checks for exactly this, and
also **executes every code cell**, so a notebook cannot rot into prose that reads correctly
against an API that has moved.
