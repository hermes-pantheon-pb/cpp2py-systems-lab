"""M_TEMPLATE · Test harness template."""

from __future__ import annotations

from types import ModuleType

import pytest


@pytest.mark.criterion("C1")
def test_c1_functional_parity(impl: ModuleType) -> None:
    assert impl.run_work() in ("naive", "idiomatic")


@pytest.mark.criterion("C2")
def test_c2_systems_property(impl: ModuleType) -> None:
    assert impl.run_work() == "idiomatic"
