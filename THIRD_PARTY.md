# Third-party components

Everything in this repository that is not ours, what licence it carries, and how it arrives.

Two categories, and the distinction matters: **vendored** code ships in this tree and is
diffable against its upstream; **fetched** code is installed by a script and stays under its own
licence, in its own environment.

---

## Vendored

### RGFN (Reaction-GFlowNet) — `third_party/rgfn/`

| | |
|---|---|
| Licence | MIT (`third_party/rgfn/LICENSE`) |
| Copyright | 2024 Michał Koziarski, Andrei Rekesh, Dmytro Shevchuk, Almer van der Sloot, Piotr Gaiński, Yoshua Bengio, Cheng-Hao Liu, Mike Tyers, Robert A. Batey |
| Upstream | <https://github.com/koziarskilab/RGFN> |
| Paper | *RGFN: Synthesizable Molecular Generation Using GFlowNets*, [arXiv:2406.08506](https://arxiv.org/abs/2406.08506) |
| Modified | **No.** See [`docs/PATCHES.md`](docs/PATCHES.md) for how to verify |

Vendored rather than fetched because `hubbatching.adapters.rgfn_adapter` and
`hubbatching.chemistry.reaction_data_factory` import it directly, and a reader reproducing a
figure should not have to resolve a second repository at a matching commit. It stays importable
as top-level `rgfn` because its own internal imports say so — renaming it into a sub-package
would mean editing upstream, which is exactly what vendoring is meant to avoid.

It is an **optional** dependency: `pip install hubbatching` does not require it, and everything
except running a generator works without it.

Upstream's gin configs are vendored alongside at `third_party/rgfn_configs/`, also unmodified.

### Chemistry library — `data/libraries/glue_standard_v1/`

418 priced building blocks and 112 reaction templates with yields, repackaged into this
repository's canonical format from an existing public set. `manifest.json` records the source
and checksums. Redistributed as data under the terms of its origin; see the manifest.

---

## Fetched, not vendored

Baseline generators and competing retrosynthesis planners used for comparison are **not** in
this tree. They are large, they have mutually incompatible dependencies, and several are
research code that pins old versions of common libraries. `setup/` installs them, each into its
own environment, and each stays under its own licence.

Nothing in `src/hubbatching/`, `reproduce/`, or the notebooks needs any of them. They are
required only to re-run the full published head-to-head — see
[`benchmarks/README.md`](benchmarks/README.md).

| component | role | licence | install |
|---|---|---|---|
| SPARROW | retrosynthesis-aware library selection — the competing planner | MIT | `setup/fetch_sparrow.sh` |
| AiZynthFinder | retrosynthetic route recovery for route-less generators | MIT | `setup/fetch_aizynth.sh` |
| Baseline generators | the other entrants in the comparison | various | `setup/fetch_generators.sh` |

Run `setup/README.md` first — it says which of these you actually need for what you are trying
to do, which is usually none of them.

---

## Runtime dependencies

Declared in `pyproject.toml`, installed by pip, not redistributed here.

| | packages | licence |
|---|---|---|
| core | rdkit | BSD-3-Clause |
| `[generators]` | torch, gin-config | BSD-3-Clause, Apache-2.0 |
| `[figures]` | matplotlib | PSF-based |
| `[notebooks]` | jupyter, pandas | BSD-3-Clause |

---

## This work

Apache-2.0 (`LICENSE`). See `NOTICE` and `CITATION.cff`.
