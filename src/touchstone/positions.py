# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""Where in a YAML file a key was written.

`yaml.safe_load` returns the data and throws the positions away, which is why every
problem this tool reported used to name a pack and leave the reader to find it. Composing
the same text keeps the node tree, and every node carries the mark it was parsed from.

This is read a second time rather than replacing the load, because the loaded document is
what gets validated and a position is only wanted when something is already wrong. A file
that composes differently from how it loaded, or does not compose at all, gives up and
returns None, since a problem reported at the wrong line is worse than one reported at no
line.
"""

from collections.abc import Sequence
from pathlib import Path

import yaml

Step = str | int
"""A mapping key or a sequence index, in the order they are written."""


def load_source(path: Path) -> str | None:
    """The text of a file, or None where it cannot be read. Never raises: a position is a
    convenience and losing it must not turn a reported problem into a crash."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def locate(source: str | None, steps: Sequence[Step]) -> tuple[int, int] | None:
    """The 1-indexed line and column of what `steps` addresses, or None.

    A final mapping key resolves to the key itself rather than to its value, because that
    is what an editor underlines and what a reader is looking for.
    """
    if source is None:
        return None
    try:
        node = yaml.compose(source)
    except yaml.YAMLError:
        return None
    if node is None:
        return None

    for depth, step in enumerate(steps):
        last = depth == len(steps) - 1
        found = _descend(node, step, key_itself=last)
        if found is None:
            return None
        node = found

    return node.start_mark.line + 1, node.start_mark.column + 1


def first(source: str | None, *candidates: Sequence[Step]) -> tuple[int, int] | None:
    """The first candidate that resolves, so a check can ask for the exact key and fall
    back to the block containing it rather than reporting no position at all."""
    for steps in candidates:
        found = locate(source, steps)
        if found is not None:
            return found
    return None


def _descend(node: yaml.Node, step: Step, key_itself: bool) -> yaml.Node | None:
    if isinstance(node, yaml.MappingNode) and isinstance(step, str):
        for key, value in node.value:
            if isinstance(key, yaml.ScalarNode) and key.value == step:
                return key if key_itself else value
        return None

    if isinstance(node, yaml.SequenceNode) and isinstance(step, int):
        indexable = 0 <= step < len(node.value)
        return node.value[step] if indexable else None

    return None
