"""M1-L01 · IDIOMATIC reference (spoiler).

Ownership flows downward through a list (strong refs); the upward edge is a
`weakref.ref`, Python's equivalent of a non-owning pointer that becomes `None`
instead of dangling.
"""

from __future__ import annotations

import weakref
from collections.abc import Iterator


class Node:
    # Fixed layout (M2 preview). "__weakref__" must be listed explicitly or slotted
    # instances cannot be weakly referenced.
    __slots__ = ("name", "_parent", "_children", "__weakref__")

    def __init__(self, name: str) -> None:
        self.name = name
        self._parent: weakref.ref[Node] | None = None
        self._children: list[Node] = []

    @property
    def parent(self) -> Node | None:
        return None if self._parent is None else self._parent()

    @property
    def children(self) -> Iterator[Node]:
        return iter(self._children)

    def add_child(self, child: Node) -> Node:
        child._parent = weakref.ref(self)  # non-owning back-edge
        self._children.append(child)  # owning edge
        return child

    def path(self) -> str:
        parent = self.parent
        return self.name if parent is None else f"{parent.path()}/{self.name}"
