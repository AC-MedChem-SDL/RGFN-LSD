"""One canonical synthesis-step schema, shared by every producer of a route.

WHY THIS MODULE EXISTS. Three different places need to write "the step
that turns molecule X into molecule Y": recipe logging, ``fragments_<N>.json`` routes, and
``enum_children.json`` children[].reaction. If they disagree by even a key name, a route assembled
from a mix of them prices the wrong molecule. The layering rule is that analysis code may
import from the core but never the reverse, so the shared definition lives HERE for the
enumeration path and the artifact writers to use the same one.

Deliberately dependency-free — no RDKit, no torch, no rgfn env — so importing it costs nothing and
neither side has a reason to keep a private copy.
"""

from typing import Dict


def reaction_id(reaction) -> str:
    """A stable identifier for a reaction/template object, whatever flavour it is."""
    if reaction is None:
        return ""
    for attr in ("name", "reaction_name", "smarts"):
        v = getattr(reaction, attr, None)
        if v:
            return str(v)
    inner = getattr(reaction, "reaction", None)
    if inner is not None:
        for attr in ("name", "smarts"):
            v = getattr(inner, attr, None)
            if v:
                return str(v)
    return str(reaction)


def reaction_step(act) -> Dict:
    """The synthesis step for a ``ReactionActionC``-shaped action.

    Returns reaction id + reactant fragments + input molecule + product, which is exactly what a
    route assembler needs to extend a hub's prefix into a child's full route.
    """
    return {
        "reaction": reaction_id(getattr(act, "input_reaction", None)),
        "reactants": [
            f.smiles
            for f in getattr(act, "input_fragments", ()) or ()
            if getattr(f, "smiles", None)
        ],
        "input": getattr(getattr(act, "input_molecule", None), "smiles", None),
        "product": getattr(getattr(act, "output_molecule", None), "smiles", None),
    }
