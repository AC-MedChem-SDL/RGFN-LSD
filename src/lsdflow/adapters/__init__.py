"""Generator-specific code -- the only place the method touches a backbone.

Everything above this package is generator-agnostic: it operates on
:class:`~lsdflow.records.FlowRecord` and :class:`~lsdflow.dag.LiteHubDAG`, which any
generator can be made to emit. These modules are what produce them for a particular
model, and they are the only modules that import ``torch`` or ``rgfn``.

Keeping the boundary here is what lets the cost model and the selection logic be
audited -- and the published numbers re-derived -- without a deep-learning stack.
"""
