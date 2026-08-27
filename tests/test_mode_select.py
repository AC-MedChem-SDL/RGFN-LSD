"""Tests for what counts as a mode.

"Modes delivered at a fixed reaction budget" is the paper's primary readout, so the
definition of a mode *is* the metric. Both halves are load-bearing and Logs/054
measured what dropping either one does: without the reward gate the method looks 13%
cheaper while 91% of the delivered library sits below the bar; without the diversity
filter it looks 12% cheaper while a 300-molecule library collapses to 39 genuinely
distinct ones. Priced per molecule worth keeping, those "savings" cost 9.8x and 6.8x.

The reward-gate tests need no chemistry and always run. The Tanimoto tests need RDKit
and skip without it.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hubbatching.mode_select import passes_reward_gate  # noqa: E402

# Two genuinely different scaffolds, and a near-duplicate of the first.
BENZ = "c1ccccc1C(=O)NC1CCCCC1"
BENZ_METHYL = "c1ccccc1C(=O)NC1CCCC(C)C1"
PYRIDINE = "OCCN1CCN(CC1)c1ncccn1"


class TestRewardGate:
    def test_higher_is_better_admits_at_and_above(self) -> None:
        assert passes_reward_gate(7.0, 7.0, higher_is_better=True)
        assert passes_reward_gate(7.1, 7.0, higher_is_better=True)
        assert not passes_reward_gate(6.9, 7.0, higher_is_better=True)

    def test_lower_is_better_inverts(self) -> None:
        """Docking targets are lower-is-better. Getting this backwards qualifies
        everything silently, which is why the direction travels with the gate."""
        assert passes_reward_gate(-8.0, -8.0, higher_is_better=False)
        assert passes_reward_gate(-9.5, -8.0, higher_is_better=False)
        assert not passes_reward_gate(-7.0, -8.0, higher_is_better=False)

    def test_none_threshold_admits_everything(self) -> None:
        """The reward-filter ablation of Logs/054 -- available, and clearly labelled."""
        assert passes_reward_gate(-999.0, None)
        assert passes_reward_gate(999.0, None, higher_is_better=False)

    def test_nan_never_passes_either_direction(self) -> None:
        """A failed docking returns NaN. It must not become a mode by comparing false."""
        assert not passes_reward_gate(math.nan, 7.0, higher_is_better=True)
        assert not passes_reward_gate(math.nan, -8.0, higher_is_better=False)

    def test_nan_passes_when_the_gate_is_ablated_and_that_is_deliberate(self) -> None:
        """Documented behaviour: NaN never passes a *set* gate, but ``None`` means no
        gate at all. Worth knowing when reading Logs/054's reward-filter ablation --
        that arm admits molecules whose docking failed, which makes the ablation look
        cheaper still, so its measured penalty is if anything understated."""
        assert passes_reward_gate(math.nan, None)


class TestDiversityFilter:
    @pytest.fixture(autouse=True)
    def _needs_rdkit(self):
        pytest.importorskip("rdkit", reason="RDKit required for fingerprints")

    def selector(self, **kw):
        from hubbatching.mode_select import DiverseThresholdModeSelector
        kw.setdefault("reward_threshold", 7.0)
        kw.setdefault("similarity", 0.5)
        return DiverseThresholdModeSelector(**kw)

    def test_first_qualifying_molecule_is_accepted(self) -> None:
        assert self.selector().accept(BENZ, 8.0)

    def test_below_gate_is_rejected_however_novel(self) -> None:
        sel = self.selector()
        assert not sel.accept(PYRIDINE, 1.0)

    def test_identical_molecule_is_rejected_the_second_time(self) -> None:
        sel = self.selector()
        assert sel.accept(BENZ, 8.0)
        assert not sel.accept(BENZ, 8.0)

    def test_distinct_scaffold_is_accepted(self) -> None:
        sel = self.selector()
        assert sel.accept(BENZ, 8.0)
        assert sel.accept(PYRIDINE, 8.0)

    def test_a_looser_cutoff_accepts_at_least_as_much(self) -> None:
        """Monotonicity in the cutoff. If this inverts, every tau sweep is unreadable."""
        strict, loose = self.selector(similarity=0.3), self.selector(similarity=0.9)
        pool = [(BENZ, 8.0), (BENZ_METHYL, 7.9), (PYRIDINE, 7.8)]
        n_strict = sum(strict.accept(s, r) for s, r in pool)
        n_loose = sum(loose.accept(s, r) for s, r in pool)
        assert n_loose >= n_strict

    def test_rejection_does_not_consume_a_slot(self) -> None:
        """A rejected molecule must not join the accepted set and block later ones."""
        sel = self.selector()
        assert not sel.accept(PYRIDINE, 1.0)      # below gate
        assert sel.accept(PYRIDINE, 8.0)          # same molecule, now qualifying
