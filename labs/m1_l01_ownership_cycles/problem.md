# M1-L01 · Ownership Cycles: Tree with Parent Links

## Problem

Port a hierarchical `Node` type (think: scene graph, DOM, config tree) from C++ to Python.
Each node owns its children; each child can navigate back to its parent.

### Required API

| Member | Semantics |
|:---|:---|
| `Node(name: str)` | Create a detached node |
| `add_child(child: Node) -> Node` | Attach `child`, return it |
| `parent` | The parent `Node`, or `None` for a root **or if the parent no longer exists** |
| `children` | Iterable of direct children, in insertion order |
| `path() -> str` | `"root/a/b"` style path |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), ownership is explicit: `std::unique_ptr` children (owning,
downward) and a raw `Node*` back-pointer (non-owning, upward). Destroying the root destroys the
whole tree **deterministically**, and the back-pointer never extends anyone's lifetime.

## The Naive Translation

[naive.py](./naive.py) maps both pointers to plain Python attributes. In Python *every* reference
is owning (it increments `ob_refcnt`), so the "non-owning" back-pointer becomes an owning one:

```text
root ──children──▶ a          refcount(root) ≥ 1 forever (a.parent)
  ▲                │          refcount(a)    ≥ 1 forever (root.children)
  └────parent──────┘          ⇒ reference cycle: refcounting can never free it
```

The tree is only reclaimed when the **cyclic GC** happens to run — non-deterministically, after
an allocation threshold, possibly never in a latency-tuned service that disabled or froze the GC.

## Your Task

Refactor [solution.py](./solution.py) (initially a copy of the naive version) so that:

1. Ownership is **downward only**: the parent→children edge is the only strong edge.
2. The back-edge does not affect lifetime.
3. A child that outlives its parent observes `parent is None` — Python's safe equivalent of the
   dangling-pointer bug the C++ version would have.

> **Hint:** Look at `weakref.ref` and how it behaves after its referent is deallocated.
> Consider `__slots__` too, but remember what slotted classes need in order to be weak-referenceable.

## Verification

```bash
./lab.py test M1-L01                    # your solution
./lab.py test M1-L01 --target naive     # watch the naive version fail C2–C5
```

| Criterion | Probe |
|:---|:---|
| C2 lifetime | `gc_disabled()` + weakrefs to every node, then `del root` |
| C3 ownership | `refcount_delta(parent, lambda: parent.add_child(...)) == 0` |
| C4 memory | `measure_alloc()` net bytes after build-and-drop |
| C5 safety | Hold a child, drop the root, read `child.parent` |
