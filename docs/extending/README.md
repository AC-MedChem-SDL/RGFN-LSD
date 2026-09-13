# Extending hub-batching

Five things people usually want to change. Each has a page, each page is a worked example, and
each corresponds to a notebook you can run.

| I want to… | page | notebook | needs |
|---|---|---|---|
| use my own generator's output | [generators.md](generators.md) | [`03`](../../notebooks/03_bring_your_own_generator.ipynb) | files on disk |
| score molecules with my own oracle | [rewards.md](rewards.md) | [`04`](../../notebooks/04_bring_your_own_reward.ipynb) | CPU |
| change how hubs are chosen | [strategies.md](strategies.md) | [`02`](../../notebooks/02_bring_your_own_strategy.ipynb) | CPU |
| swap the fragments and reactions | [chemistry.md](chemistry.md) | [`05`](../../notebooks/05_bring_your_own_chemistry.ipynb) | CPU |
| get a bench plan out | [export.md](export.md) | [`06`](../../notebooks/06_export_a_bench_plan.ipynb) | CPU |

## The shape of the thing

```
  your generator  ──pool──▶  selection strategy  ──ordered library──▶  evaluator  ──▶  cost
       │                            │                                      │
   generators.md              strategies.md                         benchmarks/README.md
   rewards.md                 (+ child and mode policies)
   chemistry.md
```

Three stages, two contracts between them, and every stage is swappable without touching the
others. That is the design: the first contract is a file format (`docs/INPUT_CONTRACT.md`), the
second is a pair of Python dataclasses (`hubbatching.eval.LibrarySet` → `EvaluationResult`).

## Two rules that make extension safe

**The core is generator-agnostic and stays that way.** Everything above
`hubbatching.adapters` operates on `FlowRecord` and `LiteHubDAG`, which any model can be made to
emit. Only `adapters/` imports torch or rgfn. If you find yourself needing a model-specific
import outside `adapters/`, the abstraction is in the wrong place — say so rather than working
around it.

**The cost model is dependency-free and stays that way.** `hubbatching.cost` imports nothing but
the standard library, so the number a paper quotes can be audited without installing a
deep-learning stack. This is enforced in CI.

## Start here

```bash
pip install -e .
hubbatching demo
```

That runs the whole pipeline on 432 real molecules in a few seconds, with no GPU and no
downloads, and prints what each stage produced. Every page below assumes you have seen it.
