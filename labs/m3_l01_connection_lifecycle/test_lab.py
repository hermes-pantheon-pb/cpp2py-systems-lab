"""M3-L01 · Verification harness for deterministic resource cleanup.

Run:  ./lab.py test M3-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

from types import ModuleType

import pytest

from harness import gc_disabled


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_send_recv_and_status(impl: ModuleType) -> None:
    conn = impl.ManagedConnection("127.0.0.1:8080")
    assert not conn.is_closed
    conn.send("ping")
    assert conn.recv() == "ping"
    conn.close()
    assert conn.is_closed


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_deterministic_close_on_exit(impl: ModuleType) -> None:
    with gc_disabled():
        with impl.ManagedConnection("127.0.0.1:8080") as conn:
            conn.send("hello")
            assert not conn.is_closed
        assert conn.is_closed, "Connection was not closed upon exiting with-statement"


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_close_on_exception_and_propagate(impl: ModuleType) -> None:
    conn_holder = []
    with pytest.raises(ValueError, match="simulated failure"):
        with impl.ManagedConnection("127.0.0.1:8080") as conn:
            conn_holder.append(conn)
            raise ValueError("simulated failure")

    assert len(conn_holder) == 1
    assert conn_holder[0].is_closed, (
        "Connection was not closed when an exception was raised inside with-statement"
    )


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_callback_cycle_deterministic_cleanup(impl: ModuleType) -> None:
    with gc_disabled():
        conn = impl.ManagedConnection("127.0.0.1:8080")
        # Form a circular reference: conn -> callback -> conn
        conn.register_listener(lambda: conn.send("ack"))

        # In idiomatic code, exiting the with-block deterministically closes the connection,
        # completely immune to reference cycles
        with conn:
            assert not conn.is_closed

        assert conn.is_closed, (
            "Connection remained open! A reference cycle prevented __del__ cleanup. "
            "Implement __enter__ and __exit__ to ensure deterministic release."
        )


# --------------------------------------------------------------------------- C5
@pytest.mark.criterion("C5")
def test_send_on_closed_raises(impl: ModuleType) -> None:
    conn = impl.ManagedConnection("127.0.0.1:8080")
    conn.close()
    with pytest.raises(RuntimeError, match="Connection closed"):
        conn.send("fail")
    with pytest.raises(RuntimeError, match="Connection closed"):
        conn.recv()
