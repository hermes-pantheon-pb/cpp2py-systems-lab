"""M1-L01 · NAIVE translation — the raw `Node*` back-pointer became a strong reference.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations


class Node:
    def __init__(self, name: str) -> None:
        self.name = name
        self.parent: Node | None = None  # "Node* parent_" … but this one OWNS
        self.children: list[Node] = []

    def add_child(self, child: Node) -> Node:
        child.parent = self  # strong back-edge → parent <-> child cycle
        self.children.append(child)
        return child

    def path(self) -> str:
        if self.parent is None:
            return self.name
        return f"{self.parent.path()}/{self.name}"
