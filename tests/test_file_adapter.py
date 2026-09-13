"""The file contract is the public integration surface, so its failures must be loud.

Every test here is written against a failure that would otherwise be silent. A missing column,
a hub absent from ``compositions.json``, an empty ``routes.json`` -- each of those lets a run
complete and produce plausible numbers that are wrong. The point of the adapter is to convert
them into errors at the point of reading.
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

import pytest

from hubbatching.adapters.file_adapter import (
    FileAdapter,
    MalformedContract,
    MissingContractFile,
    load_enumerated_hubs,
    load_flow_records,
)

REC_COLS = [
    "hub_key",
    "child_key",
    "reward",
    "log_reward",
    "log_pf_move",
    "log_pb_move",
    "log_pf_stop",
    "hub_depth",
    "hub_stereo_key",
    "child_stereo_key",
]


def _write_records(path: Path, rows, cols=REC_COLS):
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _row(hub="CC(=O)O", child="CC(=O)NC", **kw):
    base = dict(
        hub_key=hub,
        child_key=child,
        reward=0.9,
        log_reward=7.2,
        log_pf_move=-2.5,
        log_pb_move=-0.4,
        log_pf_stop=-0.1,
        hub_depth=1,
        hub_stereo_key=hub,
        child_stereo_key=child,
    )
    base.update(kw)
    return base


@pytest.fixture
def contract_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sample"
    d.mkdir()
    _write_records(d / "records.csv", [_row(), _row(child="CC(=O)NCC")])
    (d / "meta.json").write_text(
        json.dumps({"model": "test", "reward_name": "toy", "log_z": 3.0, "higher_is_better": True})
    )
    (d / "routes.json").write_text(json.dumps({"CC(=O)NC": {"seed": "CC(=O)O", "steps": []}}))
    return d


# --------------------------------------------------------------------- required files
def test_missing_records_names_the_file_and_why(tmp_path: Path):
    (tmp_path / "meta.json").write_text("{}")
    with pytest.raises(MissingContractFile) as exc:
        load_flow_records(tmp_path / "records.csv")
    assert "records.csv" in str(exc.value)


def test_missing_meta_is_refused_rather_than_defaulted(tmp_path: Path):
    """log_z and the reward direction change the answer; defaulting them would be silent."""
    d = tmp_path / "sample"
    d.mkdir()
    _write_records(d / "records.csv", [_row()])
    with pytest.raises(MissingContractFile):
        FileAdapter(str(d))


def test_missing_column_is_named(tmp_path: Path):
    cols = [c for c in REC_COLS if c != "log_pf_stop"]
    _write_records(tmp_path / "records.csv", [_row()], cols=cols)
    with pytest.raises(MalformedContract) as exc:
        load_flow_records(tmp_path / "records.csv")
    assert "log_pf_stop" in str(exc.value)


def test_extra_columns_are_allowed(tmp_path: Path):
    """Readers parse by NAME, so a writer may add columns without breaking anything."""
    cols = REC_COLS + ["log_pf_prefix", "provenance"]
    row = _row()
    row.update(log_pf_prefix=-1.0, provenance="run7")
    _write_records(tmp_path / "records.csv", [row], cols=cols)
    records = load_flow_records(tmp_path / "records.csv")
    assert len(records) == 1
    assert records[0].log_pf_stop == pytest.approx(-0.1)


# --------------------------------------------------------------------- routes
def test_empty_routes_warns_loudly(contract_dir: Path):
    """The failure this exists to prevent: a route-less run that exits 0 and looks fine.

    Routes are NOT recoverable after sampling ends, so a warning at read time is the last cheap
    place to catch it.
    """
    (contract_dir / "routes.json").write_text("{}")
    adapter = FileAdapter(str(contract_dir))
    with pytest.warns(UserWarning, match="routes"):
        adapter.sample_flow_records()


def test_declaring_no_routes_silences_the_warning(contract_dir: Path):
    """A generator with genuinely no routes must be able to say so, rather than stay silent."""
    (contract_dir / "routes.json").write_text("{}")
    adapter = FileAdapter(str(contract_dir), routes_expected=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        adapter.sample_flow_records()  # must not raise


# --------------------------------------------------------------------- validate()
def test_validate_reports_stages_and_blockers(contract_dir: Path):
    report = FileAdapter(str(contract_dir)).validate()
    assert report["can_rank_hubs"] is True
    assert report["can_hub_batch"] is False  # no enum_children.json
    assert report["can_export_bench_plan"] is False
    assert any("enum_children" in b for b in report["blockers"])


def test_validate_all_green_when_everything_present(contract_dir: Path):
    (contract_dir / "enum_children.json").write_text(
        json.dumps({"hubs": [{"hub_key": "CC(=O)O", "depth": 1, "children": []}]})
    )
    report = FileAdapter(str(contract_dir)).validate()
    assert report["can_export_bench_plan"] is True
    assert report["blockers"] == []


# --------------------------------------------------------------------- enum_children
def test_enum_children_preserves_hub_order(tmp_path: Path):
    """Hub order IS the strategy. Re-sorting here would silently substitute a different one."""
    keys = ["C", "CC", "CCC"]
    (tmp_path / "enum.json").write_text(
        json.dumps({"hubs": [{"hub_key": k, "depth": 1, "children": []} for k in keys]})
    )
    hubs = load_enumerated_hubs(tmp_path / "enum.json")
    assert [h.hub_key for h in hubs] == keys


def test_enum_children_accepts_a_bare_list(tmp_path: Path):
    (tmp_path / "enum.json").write_text(json.dumps([{"hub_key": "C", "depth": 1, "children": []}]))
    assert len(load_enumerated_hubs(tmp_path / "enum.json")) == 1


def test_enum_children_rejects_the_wrong_shape(tmp_path: Path):
    (tmp_path / "enum.json").write_text(json.dumps({"not_hubs": 3}))
    with pytest.raises(MalformedContract):
        load_enumerated_hubs(tmp_path / "enum.json")
