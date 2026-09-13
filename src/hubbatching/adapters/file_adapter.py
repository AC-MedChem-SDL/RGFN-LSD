"""``FileAdapter`` -- attach a generator that hub-batching never has to import.

This is the recommended way to bring your own model, and it is how the published work was
actually done. A generator runs in **its own environment**, writes a directory of plain CSV and
JSON, and hub-batching reads that directory. No shared interpreter, no dependency negotiation,
no co-import. The writer side is :mod:`hubbatching.adapters.artifacts`, which is pure stdlib
precisely so it imports inside whatever environment your model needs.

The contract, in full (``docs/INPUT_CONTRACT.md`` has the column-level detail)::

    <sample-dir>/
      records.csv         REQUIRED  one row per observed hub -> terminal-child transition,
                                    carrying the four log-terms flow recovery needs
      meta.json           REQUIRED  log_z, higher_is_better, model, reward_name
      compositions.json   optional  per-molecule promoted-fragment composition (dynamic
                                    libraries only; absent means every block is base stock)
      routes.json         optional  per-molecule synthesis route -- REQUIRED to export a bench
                                    plan, and unrecoverable after the fact (see below)
      visit_counts.json   optional  per-hub trajectory visit counts, for the reward-free
                                    visitation estimator
      enum_children.json  optional  exhaustive one-reaction children of each ranked hub;
                                    required for hub-batching, not for best-candidate

**Only ``records.csv`` and ``meta.json`` are required to rank hubs.** You can integrate a model
with those two alone, see its flow field, and decide whether the rest is worth wiring.

**On ``routes.json``, which is the one people skip.** It is optional to this class and
effectively mandatory in practice: the route is what turns a selected library into something a
chemist can make, and it is *not recoverable later* -- the trajectory is gone once sampling
ends, and ``compositions.json`` keeps only a reaction count. In this project three of four
generators took the default, wrote a well-formed empty file, exited zero, and were promoted;
the loss surfaced months later and cost a full re-sample of 36 of 40 cell-seeds. So
:meth:`validate` warns loudly when a route-bearing generator emits none, and the exporter
refuses outright. If your generator genuinely has no synthesis routes -- a fragment-attachment
model, say -- declare that explicitly via ``routes_expected=False`` rather than leaving the file
empty and hoping the reader notices.

Keys must come from one key function throughout. A route keyed differently from its hub is
worse than no route at all: the lookup silently returns nothing and the caller prices the hub
instead of the child, with no error anywhere.
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path
from typing import Dict, List, Optional

from hubbatching.adapters.contract import FlowSample, GFNAdapter
from hubbatching.campaign import EnumChild, EnumeratedHub, RxChild
from hubbatching.records import FlowRecord

# Columns ``records.csv`` must carry. Kept in step with
# ``hubbatching.adapters.artifacts.REC_COLS`` -- the writer and the reader are two halves of one
# contract and drifting them apart is the failure this module exists to prevent.
REQUIRED_RECORD_COLS = (
    "hub_key",
    "child_key",
    "reward",
    "log_reward",
    "log_pf_move",
    "log_pb_move",
    "log_pf_stop",
    "hub_depth",
)


class MissingContractFile(FileNotFoundError):
    """A required file is absent from the sample directory."""


class MalformedContract(ValueError):
    """A contract file exists but does not carry what it must."""


def _read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open() as fh:
        return json.load(fh)


def _float(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    if raw is None or raw == "":
        return default
    return float(raw)


def load_flow_records(records_csv: Path) -> List[FlowRecord]:
    """Parse ``records.csv`` into :class:`~hubbatching.records.FlowRecord` objects.

    Every column is read **by name**, never by position, so a writer may add columns (the
    Z-anchored prefix terms, a provenance tag) without breaking this reader.
    """
    if not records_csv.exists():
        raise MissingContractFile(
            f"{records_csv} not found. records.csv is the one file hub ranking cannot do "
            "without -- see docs/INPUT_CONTRACT.md."
        )
    with records_csv.open() as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_RECORD_COLS if c not in (reader.fieldnames or [])]
        if missing:
            raise MalformedContract(
                f"{records_csv} is missing required column(s): {missing}. "
                f"Present: {reader.fieldnames}. See docs/INPUT_CONTRACT.md."
            )
        records = []
        for row in reader:
            records.append(
                FlowRecord(
                    hub_key=row["hub_key"],
                    child_key=row["child_key"],
                    reward=_float(row, "reward"),
                    log_reward=_float(row, "log_reward"),
                    log_pf_move=_float(row, "log_pf_move"),
                    log_pb_move=_float(row, "log_pb_move"),
                    log_pf_stop=_float(row, "log_pf_stop"),
                    hub_depth=int(_float(row, "hub_depth")),
                    hub_stereo_key=row.get("hub_stereo_key", "") or row["hub_key"],
                    child_stereo_key=row.get("child_stereo_key", "") or row["child_key"],
                )
            )
    return records


def load_enumerated_hubs(
    enum_children_json: Path,
    *,
    compositions: Optional[Dict[str, dict]] = None,
    with_reactions: bool = False,
) -> List[EnumeratedHub]:
    """Parse ``enum_children.json`` into the hub-batching input.

    **Hub order in this file is the strategy.** Hub-batching walks it top to bottom, so the
    sequence a ranking produced is carried by the file itself; re-sorting it here would silently
    substitute a different strategy for the one that was run.

    Args:
        compositions: ``compositions.json``, used to attach each hub's own promoted fragments.
            Omit and hubs carry none -- correct for a generator with no dynamic library, and
            **wrong** for one that has it, because a hub with no promoted fragments prices as
            though its scaffold were free.
        with_reactions: also read each child's final reaction, returning :class:`RxChild`
            instead of :class:`EnumChild`. Needed to export a bench plan; ignored by selection.

    There is deliberately ONE loader rather than a plain one and a reaction-carrying one. Two
    implementations over the same file drift, and when they do every downstream artifact
    describes a library that was never selected -- with nothing raising. The research prototype
    had two and needed a parity assertion between them to stay honest; this has one and does not.
    """
    comps = compositions or {}
    payload = _read_json(enum_children_json)
    if payload is None:
        raise MissingContractFile(
            f"{enum_children_json} not found. Hub-batching needs each ranked hub's enumerated "
            "children; best-candidate does not. See docs/INPUT_CONTRACT.md."
        )
    hubs_raw = payload.get("hubs") if isinstance(payload, dict) else payload
    if not isinstance(hubs_raw, list):
        raise MalformedContract(
            f"{enum_children_json} should be {{'hubs': [...]}} or a bare list of hubs; "
            f"got a {type(payload).__name__}."
        )
    if with_reactions:
        # Imported here, not at module scope: naming pulls the reaction table, and reading a
        # contract directory must not require it.
        from hubbatching.export.naming import named_reaction, parse_template

    hubs: List[EnumeratedHub] = []
    for h in hubs_raw:
        children: List[EnumChild] = []
        for c in h.get("children", []):
            common = dict(
                smiles=c["smiles"],
                reward=float(c["reward"]),
                added_promoted=tuple(c.get("added_promoted", ()) or ()),
            )
            if not with_reactions:
                children.append(EnumChild(**common))
                continue
            steps = c.get("reaction") or []
            # The FINAL step is the diversifying reaction. An enumerated child is one reaction
            # off its hub, so there is normally exactly one; taking the last regardless means a
            # multi-step child (which would mean the enumeration changed shape) still names the
            # step that actually differs rather than silently naming the wrong one.
            last = steps[-1] if steps else {}
            template = last.get("reaction", "") or ""
            template_id, _ = parse_template(template) if template else ("", None)
            # Prefer a name the generator supplied over one inferred from the template. The
            # inference table recognises RGFN-format templates; another generator's SMARTS will
            # not match it and would silently come out as "?", printing a SMARTS string at a
            # chemist in every exported protocol. A generator that knows its own chemistry
            # should be able to say so, so ``reaction_name`` on the step wins when present.
            explicit = (last.get("reaction_name") or "").strip()
            if explicit:
                named = explicit
            elif template:
                named = named_reaction(template)
            else:
                named = "(no reaction recorded)"
            children.append(
                RxChild(
                    **common,
                    named=named,
                    template_id=template_id,
                    reagents=tuple(last.get("reactants", ()) or ()),
                    parent_input=last.get("input", "") or "",
                    template=template,
                    product=last.get("product", "") or "",
                )
            )
        hub_comp = comps.get(h["hub_key"], {}) or {}
        hubs.append(
            EnumeratedHub(
                hub_key=h["hub_key"],
                depth=int(h.get("depth", 0)),
                promoted=tuple(h.get("promoted") or hub_comp.get("promoted", ()) or ()),
                children=children,
                hub_input=h.get("hub_input", "") or h["hub_key"],
                uncertainty=h.get("uncertainty"),
                n_effective=int(h.get("n_effective", 0) or 0),
            )
        )
    return hubs


class FileAdapter(GFNAdapter):
    """Read a generator's emitted contract directory. Imports nothing model-specific.

    Args:
        sample_dir: directory holding ``records.csv`` + ``meta.json`` (and optionally the rest).
        enum_children: path to ``enum_children.json`` if it lives outside ``sample_dir`` --
            enumeration output is often large and written somewhere else.
        routes_expected: whether this generator is supposed to produce synthesis routes. Leave
            ``True`` for any reaction-based model; set ``False`` *deliberately* for a generator
            that has no routes to give, so the absence is a declaration rather than a silence.
    """

    model_name = "files"

    def __init__(
        self,
        sample_dir: str,
        *,
        enum_children: Optional[str] = None,
        routes_expected: bool = True,
    ):
        self.sample_dir = Path(sample_dir)
        if not self.sample_dir.is_dir():
            raise MissingContractFile(f"{sample_dir} is not a directory.")
        self.enum_children_path = (
            Path(enum_children) if enum_children else self.sample_dir / "enum_children.json"
        )
        self.routes_expected = routes_expected
        self.meta = _read_json(self.sample_dir / "meta.json", default={}) or {}
        if not self.meta:
            raise MissingContractFile(
                f"{self.sample_dir / 'meta.json'} not found or empty. It carries log_z and the "
                "reward direction, both of which change the answer rather than merely labelling "
                "it. See docs/INPUT_CONTRACT.md."
            )

    # -- the GFNAdapter contract ------------------------------------------------------
    def sample_flow_records(self, n_trajectories: int = 0) -> FlowSample:
        """Load the already-sampled records. ``n_trajectories`` is accepted for interface
        compatibility and ignored -- sampling happened in the generator's own environment, and
        this adapter reads its result rather than re-running it."""
        records = load_flow_records(self.sample_dir / "records.csv")
        routes = _read_json(self.sample_dir / "routes.json", default={}) or {}
        compositions = _read_json(self.sample_dir / "compositions.json", default={}) or {}
        visit_counts = _read_json(self.sample_dir / "visit_counts.json", default={}) or {}

        if self.routes_expected and not routes:
            warnings.warn(
                f"{self.sample_dir}/routes.json is absent or empty, but this adapter was built "
                "with routes_expected=True. Hub ranking and the cost model will work; exporting "
                "a bench plan will not, and routes CANNOT be recovered later -- the trajectory "
                "is gone once sampling ends. Re-sample now, or pass routes_expected=False if "
                "this generator genuinely has no synthesis routes.",
                stacklevel=2,
            )

        return FlowSample(
            records=records,
            visit_counts=visit_counts,
            n_trajectories=int(self.meta.get("n_trajectories", 0) or 0),
            terminal_depths=[r.hub_depth for r in records],
            log_z=float(self.meta.get("log_z", 0.0) or 0.0),
            higher_is_better=bool(self.meta.get("higher_is_better", True)),
            model=str(self.meta.get("model", "files")),
            reward_name=str(self.meta.get("reward_name", "unknown")),
            compositions=compositions,
            routes=routes,
        )

    # -- hub-batching input -----------------------------------------------------------
    def enumerated_hubs(self, *, with_reactions: bool = False) -> List[EnumeratedHub]:
        """The ranked, enumerated hubs, in the order the ranking emitted them.

        ``compositions.json`` is passed through so a hub's own promoted fragments are attached;
        without them a hub with a built scaffold prices as though the scaffold were free.
        """
        comps = _read_json(self.sample_dir / "compositions.json", default={}) or {}
        return load_enumerated_hubs(
            self.enum_children_path, compositions=comps, with_reactions=with_reactions
        )

    # -- diagnostics ------------------------------------------------------------------
    def validate(self) -> Dict[str, object]:
        """Report what this directory can and cannot support, without raising.

        Use it before committing to a long run: it answers "will this get me a bench plan?"
        in a second rather than at the end of an enumeration.
        """
        records_csv = self.sample_dir / "records.csv"
        routes = _read_json(self.sample_dir / "routes.json", default={}) or {}
        report: Dict[str, object] = {
            "sample_dir": str(self.sample_dir),
            "model": self.meta.get("model", "unknown"),
            "reward_name": self.meta.get("reward_name", "unknown"),
            "has_records": records_csv.exists(),
            "has_meta": bool(self.meta),
            "has_routes": bool(routes),
            "n_routes": len(routes),
            "has_compositions": (self.sample_dir / "compositions.json").exists(),
            "has_enum_children": self.enum_children_path.exists(),
        }
        report["can_rank_hubs"] = bool(report["has_records"] and report["has_meta"])
        report["can_hub_batch"] = bool(report["can_rank_hubs"] and report["has_enum_children"])
        report["can_export_bench_plan"] = bool(report["can_hub_batch"] and report["has_routes"])
        blockers = []
        if not report["has_records"]:
            blockers.append("records.csv missing -- nothing can be ranked")
        if not report["has_meta"]:
            blockers.append("meta.json missing -- log_z and reward direction unknown")
        if not report["has_enum_children"]:
            blockers.append("enum_children.json missing -- best-candidate only, no hub-batching")
        if self.routes_expected and not routes:
            blockers.append(
                "routes.json empty -- no bench plan, and NOT recoverable without re-sampling"
            )
        report["blockers"] = blockers
        return report
