#!/bin/bash
# Install the baseline generators used in the published head-to-head.
#
# NOT needed to use hub-batching, and not needed to reproduce any figure -- reproduce/ reads
# committed artifacts. This exists so the full comparison can be re-run from scratch. See
# benchmarks/README.md before deciding you need it.
#
# Each generator installs into ITS OWN conda environment. That is not fastidiousness: no two of
# them co-import, and one ships its own fork of a package another one needs. Everything crosses
# the boundary by subprocess or by the file contract in docs/INPUT_CONTRACT.md, never by import.
set -euo pipefail

cat <<'MSG'
The baseline generators are third-party research code under their own licences, and each
needs its own conda environment.

This repository does not redistribute them. To reproduce the full comparison you will need,
per generator: the authors' repository, their environment, and their published training
configuration at the budget stated in the paper.

What this repository DOES give you, so you do not have to trust our runs:

  docs/INPUT_CONTRACT.md   the exact files any generator must emit to be compared here
  benchmarks/README.md     the pricing seam, and the rules for reading a competitor's number
  artifacts/               the committed outputs of the runs the paper reports

If you are adding a generator of your own rather than re-running ours, you want
docs/extending/generators.md -- and you do not need this script at all.
MSG
