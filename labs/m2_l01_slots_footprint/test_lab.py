"""M2-L01 · Verification harness for struct layout and memory footprint.

Run:  ./lab.py test M2-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

import array
import gc
from types import ModuleType

import pytest

from harness import measure_alloc


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_tick_attributes_and_equality(impl: ModuleType) -> None:
    t1 = impl.Tick(1_700_000_000, 150.25, 100)
    t2 = impl.Tick(1_700_000_000, 150.25, 100)
    t3 = impl.Tick(1_700_000_001, 150.25, 100)

    assert t1.ts == 1_700_000_000
    assert t1.px == 150.25
    assert t1.qty == 100

    assert t1 == t2
    assert t1 != t3
    assert hash(t1) == hash(t2)
    assert len({t1, t2, t3}) == 2


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_no_instance_dict(impl: ModuleType) -> None:
    t = impl.Tick(1_700_000_000, 100.0, 50)
    assert not hasattr(t, "__dict__"), (
        "Tick instance contains a `__dict__` attribute. "
        "Use `__slots__` or `@dataclass(slots=True)` to fix member layout."
    )


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_memory_budget_100k_instances(impl: ModuleType) -> None:
    n = 100_000
    # Pre-generate values outside the measured allocation to isolate instance overhead
    ts_vals = list(range(1_700_000_000, 1_700_000_000 + n))
    px_vals = [100.0 + (i % 50) for i in range(n)]
    qty_vals = [10 + (i % 100) for i in range(n)]

    def allocate_ticks() -> list[object]:
        return [impl.Tick(ts_vals[i], px_vals[i], qty_vals[i]) for i in range(n)]

    gc.collect()
    ticks, report = measure_alloc(allocate_ticks)
    bytes_per_instance = report.net_bytes / n

    assert bytes_per_instance <= 70.0, (
        f"Memory footprint was {bytes_per_instance:.2f} bytes/instance (budget is <= 70.0 bytes). "
        f"Naive dynamic dicts consume ~104 B/instance; fixed slots achieve ~64 B/instance."
    )
    del ticks


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_immutability(impl: ModuleType) -> None:
    t = impl.Tick(1_700_000_000, 100.0, 50)
    with pytest.raises(AttributeError):
        t.px = 200.0  # type: ignore[misc]


# --------------------------------------------------------------------------- C5
@pytest.mark.criterion("C5")
def test_export_columnar_arrays(impl: ModuleType) -> None:
    ticks = [
        impl.Tick(1_700_000_000, 100.5, 10),
        impl.Tick(1_700_000_001, 101.5, 20),
        impl.Tick(1_700_000_002, 102.5, 30),
    ]

    res = impl.export_columnar(ticks)
    assert isinstance(res, tuple) and len(res) == 3, "export_columnar must return a 3-tuple"

    ts_arr, px_arr, qty_arr = res
    assert isinstance(ts_arr, array.array) and ts_arr.typecode == "I", "ts must be array.array('I')"
    assert isinstance(px_arr, array.array) and px_arr.typecode == "d", "px must be array.array('d')"
    assert isinstance(qty_arr, array.array) and qty_arr.typecode == "I", "qty must be array.array('I')"

    assert list(ts_arr) == [1_700_000_000, 1_700_000_001, 1_700_000_002]
    assert list(px_arr) == [100.5, 101.5, 102.5]
    assert list(qty_arr) == [10, 20, 30]

    # Verify buffer protocol compatibility
    mv = memoryview(px_arr)
    assert mv.itemsize == 8 and mv.format == "d"
