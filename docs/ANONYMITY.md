# Anonymity policy

This repository is the **named** artifact: it carries real authorship, and it is
what a journal editor, a referee under single-blind review, and (after
publication) the public will see. The **anonymous** artifact for double-blind
review is not a second repository — it is a build output, produced by
`tools/make_anon_snapshot.sh`.

This file records what the requirement actually is, how the build meets it, and
what it cannot check for you.

---

## 1. The requirement, stated properly

No venue prescribes a repository layout. Double-blind review asks one thing: that
nothing a reviewer sees identifies the authors. Identity reaches a reviewer
through exactly five channels.

| # | Channel | Examples |
|---|---|---|
| 1 | **File contents** | names, emails, usernames, cluster and host names, compute-allocation codes, institution names, funding acknowledgements, experiment-tracker entities |
| 2 | **File and directory *names*** | a report named after the compute node it was written on. A content grep never finds these |
| 3 | **Git metadata** | commit author and committer name/email, tags, branch names, references to pull requests or issues |
| 4 | **Embedded binary metadata** | PDF `/Author` `/Creator` `/Title`, PNG text chunks, `docProps/core.xml` in Office files, notebook kernel paths |
| 5 | **Hosting identity** | the organisation or user account the repository lives under, project pages, a DOI (which resolves to a named record), preprint links, and traffic analytics on a repository you control |

The bar is **"no accidental identity."** Reviewers are instructed not to hunt, and
posting a preprint is permitted at the ML venues we target. That calibration
matters in both directions: it means this is a bounded engineering task rather
than an adversarial one, and it means channel 5 is solved by *how we deliver the
artifact*, not by scrubbing files.

## 2. How each channel is met

| # | Mechanism |
|---|---|
| 1, 2 | `tools/check_identity.py` scans contents **and** pathnames against `tools/identity_denylist.txt`, and separately flags machine-specific absolute paths. It runs in CI on this repo and as a hard gate inside the snapshot build |
| 3 | The snapshot is taken with `git archive HEAD` — file trees only, no history — then committed once as `Anonymous <anonymous@example.com>` with a fixed timestamp. The named repo's history is never exposed |
| 4 | The linter scans raw bytes of every binary and additionally parses PDF/PNG/Office/notebook metadata. The build normalises PDF `CreationDate`, which is a weak fingerprint and also breaks byte-reproducible figures |
| 5 | **Never link this repository in a double-blind submission.** Deliver the snapshot as supplementary material (preferred: nothing external to leak), or via an anonymising proxy with an expiry set past the discussion period |

### The load-bearing assertion

This repo permits identity in a few files (`NOTICE`, `CITATION.cff`, `README.md`,
the named workshop PDF, plus the deny-list itself and vendored upstream licences — see
`tools/identity_allowlist.txt`). The snapshot permits it **nowhere**: the build
re-runs the linter against the staged tree with an *empty* allowlist and refuses
to produce anything if a single finding survives.

That inversion is the whole design. A clean build is not a claim that we
remembered to check — it is a proof that no exempted file made it through
unmodified.

## 3. Rules that keep the build cheap

Anonymisation is expensive when identity is spread across a tree and cheap when it
is concentrated. Four rules concentrate it:

1. **No absolute paths, anywhere.** All roots resolve through one module reading
   environment variables with repo-relative defaults. This is also what makes the
   code run on a reviewer's laptop, so the rule pays for itself.
2. **Site-specific configuration is quarantined** in `cluster/`, supplied by an
   uncommitted `site.env` (with a committed `.example`). Scheduler directives
   cannot interpolate environment variables, so job payloads carry no directives:
   a single submit wrapper assembles them from `site.env`. The snapshot drops the
   whole directory.
3. **Named identity is concentrated and allowlisted.** Routine authorship lives in
   `NOTICE`, `CITATION.cff`, and marked README blocks; the named workshop PDF is the
   one binary exception and is dropped from the anonymous build. Everything else — code,
   configs, docs, tests — is identity-free as a matter of policy, not cleanup.
4. **Identity blocks are delimited.** In text files, wrap author-bearing lines in
   `<!-- IDENTITY:BEGIN -->` / `<!-- IDENTITY:END -->`; the build strips them, so
   one README stays automatically in sync with its anonymous twin.

### The escape hatch

Some lines must contain a forbidden pattern to do their job — this checker's own
test fixtures, and documentation showing an example of what *not* to write. Those
lines opt out individually:

```python
path = "OUT=/home/someone/runs\n"  # identity-check: ignore (fixture data)
```

It is line-scoped, never file-scoped, and it is the only way identity can pass the
gate. Always give a reason in the comment. If you find yourself reaching for it in
ordinary code, the code wants the path-resolution layer instead.

## 3b. Delivery, per venue

Channel 5 is settled by *how* the artifact is handed over, not by scrubbing. The
targets differ, and their requirements nest — anything built for the strictest
double-blind case satisfies the others.

| | Review | Code policy | Deliver as |
|---|---|---|---|
| **GEM (NeurIPS workshop)** | double-blind, non-archival | *"highly encouraged but not mandatory"* | supplementary zip, **50 MB cap on the whole submission** including the PDF |
| **ICLR** | double-blind, archival | optional, plus a reproducibility statement | supplementary zip, or an anonymising proxy with an expiry past discussion |
| **NCS** | single-blind, archival | **mandatory** availability statement + DOI-archived deposit | this repo, named, plus the deposit |

Rules that follow from the table:

- **Never link this repository in a double-blind submission.** A URL under a named
  organisation is non-anonymous however clean its files are.
- **The size cap is a hard limit, and it is a design constraint, not a packaging
  problem.** `make_anon_snapshot.sh --max-mb` defaults to 40, leaving headroom for
  the paper. When it trips, the answer is to move rendered assets out and keep the
  numbers they were drawn from: a reviewer needs the CSV behind a figure far more
  than the PNG of it.
- **Non-archival is not a licence to skip anonymisation.** GEM runs one round of
  double-blind review like any other venue.
- **A non-archival workshop paper does not block the later archival submissions,**
  so no DOI is needed — and none should be cited, since a deposit record shows its
  authors even when the files are restricted.

### Check the paper, not just the repo

The PDF is what actually gets desk-rejected, and it is a binary the checker
already understands — it parses `/Author`, `/Creator`, `/Title` and scans raw
bytes. LaTeX toolchains routinely embed the source path, so a build run from a
home directory can carry a username into the metadata:

```bash
python3 tools/check_identity.py --root path/to/paper --all
```

Run it on the submission directory before every upload, and on the zip's contents
after building it.

## 4. What the linter cannot check

Run these by eye before submitting:

- **Self-citation phrasing** — "in our previous work [12] we showed…" identifies
  you even with the citation intact. Cite your own prior work in the third person.
- **Acknowledgements and funding.** Belongs in the paper, not the repo, and must
  be absent from the anonymous PDF as well.
- **A preprint or a published sibling paper.** If the same result is public under
  your names, a reviewer who searches a distinctive term will find it. This is
  permitted, not a violation — but it is a reason to keep the artifact's *files*
  clean regardless: a name found inside a supposedly anonymous artifact is a
  concrete flag a reviewer can report, whereas a search hit is explicitly tolerated.
- **A DOI.** A deposit record shows title and authors even when its files are
  restricted. Do not cite a reserved DOI in an anonymous submission. Write instead:
  *"code and data are included as supplementary material; a permanent
  DOI-archived release will be provided upon acceptance."*
- **Prose that is distinctive rather than identifying** — an unusual internal
  codename, a lab-specific instrument, a named in-house dataset.

## 5. Running it

```bash
python3 tools/check_identity.py                  # gate this repo (exit 1 on findings)
python3 tools/check_identity.py --all            # ALSO see files not yet staged
python3 tools/check_identity.py --report         # inventory without failing
tools/make_anon_snapshot.sh --zip build/anon.zip # build + assert + package
git -C build/anon log --format='%an <%ae> %ad'   # confirm the history by eye
```

**Use `--all` before committing a new file.** The default reads `git ls-files`, so a
file that has never been staged is invisible to the gate. This has already bitten
once: a new test file carrying real identity as fixture data passed a local run and
was caught only by CI, which sees the tree after checkout.

Add a term to `tools/identity_denylist.txt` the moment you notice it — the file is
data, not code, and enlarging it costs nothing. Keep anything that should not
appear even in this private repo in an uncommitted
`tools/identity_denylist.local.txt`.
