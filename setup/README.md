# setup/

Fetching things that are too large, too heavy, or too licence-encumbered to live in git.

**Read the table before running anything.** Most people need none of this.

| I want to… | need any of this? |
|---|---|
| see the method work end to end | **No.** `hubbatching demo` — the toy data is committed |
| regenerate a published figure | **No.** `reproduce/` reads committed artifacts |
| run hub-batching on *my* generator's output | **No.** Write the file contract and go |
| work through the notebooks | **No**, except notebook 07 (GPU), which wants one checkpoint |
| train a generator here | `fetch_models.py` is optional; `pip install 'hubbatching[generators]'` is not |
| re-run the full published head-to-head | **Yes** — all of it. See `benchmarks/README.md` |

---

## Model checkpoints

```bash
python3 setup/fetch_models.py --list           # what exists, what you already have
python3 setup/fetch_models.py toy_rgfn_seh     # one
python3 setup/fetch_models.py --all            # everything
python3 setup/fetch_models.py --verify         # re-check what is on disk
```

Standard library only, so it works before you have installed anything, including on a bare
login node.

`models.csv` is the registry — name, URL, SHA-256, size, description — and it is **data**.
Adding a model or moving to a different host is an edit to that file, not to the script.

**Every download is checksummed and a mismatch deletes the file.** This is not defensiveness for
its own sake: a truncated checkpoint, or a proxy that returned an error page with a 200 status,
loads as a model with garbage weights and then produces plausible, wrong numbers. Nothing
downstream notices.

**Fetch from a login node.** Compute nodes are frequently air-gapped, and discovering that
inside a queued job wastes the queue wait as well as the job.

### Why Zenodo

It gives a DOI and a permanent record, which is what an archival journal's data-availability
statement actually wants. The trade-off is ergonomic — no model card, clunkier than a model hub
— which is why the URL lives behind a registry: if a mirror is added later, that is one more row
in the CSV.

Use a **specific version** URL, never the concept DOI. The concept DOI resolves to "latest", so
a later upload silently changes what an old command downloads, which is precisely the hole a
fetch script exists to close.

---

## Baseline generators and planners

```bash
setup/fetch_sparrow.sh        # the competing library planner (MILP)
setup/fetch_aizynth.sh        # retrosynthesis, for generators that log no routes
setup/fetch_generators.sh     # the other entrants in the comparison
```

Each installs into **its own conda environment**, because no two of them co-import — one ships
its own fork of a package another needs. The evaluators reach them by subprocess, never by
import. That is also why none of this is a dependency of `hubbatching`: the moment it were,
everybody would have to resolve every one of these to install anything.

Expect this to take a while and to need conda. If you only want to compare *your own selection
method* against ours, you do not need any of it — see `benchmarks/README.md` section A.

---

## One thing that fetches itself

Upstream RGFN downloads its proxy models on first use into
`third_party/rgfn/gfns/reaction_gfn/proxies/cache/` (the sEH proxy is ~2.5 MB). It is not
vendored, because it is a downloaded artifact rather than source and shipping it would break the
byte-identical-to-upstream property `docs/PATCHES.md` relies on.

Practical consequence: warm that cache from a login node before submitting an sEH job.
