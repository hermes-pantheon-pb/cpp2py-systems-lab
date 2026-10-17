"""M1-L01 · Verification harness.

Run:  ./lab.py test M1-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

import weakref
from types import ModuleType
from typing import Any

import pytest

from harness import gc_disabled, measure_alloc, refcount_delta


def build_tree(Node: Any, depth: int, fanout: int) -> tuple[Any, list[weakref.ref[Any]]]:
    """Build a complete tree; return (root, weakrefs to every node)."""
    root = Node("root")
    refs = [weakref.ref(root)]
    frontier = [root]
    for level in range(depth):
        nxt = []
        for parent in frontier:
            for i in range(fanout):
                child = parent.add_child(Node(f"n{level}_{i}"))
                refs.append(weakref.ref(child))
                nxt.append(child)
        frontier = nxt
    return root, refs


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_api_navigation(impl: ModuleType) -> None:
    root = impl.Node("root")
    a = root.add_child(impl.Node("a"))
    b = a.add_child(impl.Node("b"))
    c = root.add_child(impl.Node("c"))

    assert root.parent is None
    assert a.parent is root and b.parent is a and c.parent is root
    assert [n.name for n in root.children] == ["a", "c"]
    assert b.path() == "root/a/b"


@pytest.mark.criterion("C1")
def test_add_child_returns_child(impl: ModuleType) -> None:
    root = impl.Node("root")
    child = impl.Node("x")
    assert root.add_child(child) is child


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_tree_freed_by_refcounting_alone(impl: ModuleType) -> None:
    with gc_disabled():
        root, refs = build_tree(impl.Node, depth=3, fanout=3)
        assert all(r() is not None for r in refs)
        del root
        alive = sum(r() is not None for r in refs)
    assert alive == 0, (
        f"{alive}/{len(refs)} nodes survived `del root` with the GC disabled — "
        "a reference cycle is keeping them alive (who owns whom?)"
    )


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_add_child_does_not_retain_parent(impl: ModuleType) -> None:
    parent = impl.Node("p")
    delta = refcount_delta(parent, lambda: parent.add_child(impl.Node("c")))
    assert delta == 0, f"add_child() stored {delta} new strong reference(s) to the parent"


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_build_and_drop_retains_nothing(impl: ModuleType) -> None:
    def scenario() -> None:
        root, _ = build_tree(impl.Node, depth=3, fanout=10)  # 1 + 10 + 100 + 1000 nodes
        del root

    with gc_disabled():
        _, report = measure_alloc(scenario)
    assert report.net_bytes < 16 * 1024, (
        f"{report.net_bytes:,} bytes still allocated after the tree went out of scope"
    )


# --------------------------------------------------------------------------- C5
@pytest.mark.criterion("C5")
def test_orphan_sees_none(impl: ModuleType) -> None:
    with gc_disabled():
        root = impl.Node("root")
        child = root.add_child(impl.Node("child"))
        root_ref = weakref.ref(root)
        del root
        assert root_ref() is None, "the child is keeping its parent alive"
        assert child.parent is None
        assert child.path() == "child"
