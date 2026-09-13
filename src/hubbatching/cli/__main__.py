"""Subcommand dispatcher for ``hubbatching``.

Each subcommand owns its own ``argparse`` parser, because each has genuinely different options
and folding them into one parser would produce a help text nobody reads. This module's whole job
is to pick the right one and hand it the remaining arguments, so ``hubbatching campaign --help``
prints exactly what ``python -m hubbatching.cli.campaign --help`` prints.

Subcommand modules are imported **lazily**. ``hubbatching --help`` must work on a machine with
neither matplotlib nor torch installed; importing every driver up front would break that, and
the help text is precisely what someone in that situation is trying to read.
"""

from __future__ import annotations

import importlib
import sys
from typing import Dict, List, Optional, Tuple

# subcommand -> (module, one-line help). Order is pipeline order, not alphabetical: the list is
# also the tutorial, and sorting it would scatter the steps.
COMMANDS: Dict[str, Tuple[str, str]] = {
    "demo": (
        "hubbatching.cli.demo",
        "run the whole pipeline on the bundled toy dataset (seconds, no GPU)",
    ),
    "inspect": (
        "hubbatching.cli.inspect_contract",
        "check a generator's output directory and report what it can support",
    ),
    "pick-hubs": (
        "hubbatching.cli.pick_hubs",
        "rank hubs by recovered flow -> hubs.csv (the walk order IS the strategy)",
    ),
    "campaign": (
        "hubbatching.cli.campaign",
        "hub-batching vs best-candidate at one operating point",
    ),
    "sweep": (
        "hubbatching.cli.sweep",
        "curves over the diversity cutoff and the reaction budget",
    ),
    "surface": (
        "hubbatching.cli.surface",
        "the two-knob surface: reward bar x diversity cutoff at a fixed budget",
    ),
    "export": (
        "hubbatching.cli.export",
        "turn a selected library into a bench plan (buy lists, protocols, schemes)",
    ),
}

_USAGE = """usage: hubbatching <command> [options]

Run hub-batching on your own generator's output.

commands:
{commands}

Start with:
  hubbatching demo                 see the whole pipeline on toy data, in seconds
  hubbatching inspect <dir>        check whether your data supports what you want

`hubbatching <command> --help` for a command's own options.

Docs: docs/INPUT_CONTRACT.md (the file formats your generator must emit)
      docs/extending/          (bring your own generator, reward, strategy, chemistry)
"""


def _usage() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = [f"  {name:<{width}}  {help_}" for name, (_, help_) in COMMANDS.items()]
    return _USAGE.format(commands="\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0

    if argv[0] in ("-V", "--version"):
        from hubbatching import __version__

        print(f"hubbatching {__version__}")
        return 0

    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        # Suggest rather than just refuse -- the commands are hyphenated and the underscore
        # version is the obvious wrong guess.
        guess = command.replace("_", "-")
        hint = f" Did you mean {guess!r}?" if guess in COMMANDS else ""
        print(f"hubbatching: unknown command {command!r}.{hint}\n", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2

    module_name, _ = COMMANDS[command]
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(
            f"hubbatching {command}: could not import {module_name} ({exc}).\n"
            "This usually means an optional dependency is missing. Plotting needs "
            "`pip install 'hubbatching[figures]'`; running a generator needs "
            "`pip install 'hubbatching[generators]'`.",
            file=sys.stderr,
        )
        return 1

    # Each driver parses sys.argv itself, so present it the argv it would have seen if it had
    # been invoked directly. argv[0] keeps the subcommand name so its own usage string reads
    # correctly.
    saved = sys.argv
    sys.argv = [f"hubbatching {command}"] + rest
    try:
        result = module.main()
    finally:
        sys.argv = saved
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
