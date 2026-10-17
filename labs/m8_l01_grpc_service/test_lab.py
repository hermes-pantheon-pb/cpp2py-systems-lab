"""M8-L01 · Verification harness for in-process gRPC servicer, status codes, and deadlines.

Run:  ./lab.py test M8-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

import concurrent.futures
from types import ModuleType

import grpc
import pytest

from harness import run_concurrently
from labs.m8_l01_grpc_service import kv_pb2, kv_pb2_grpc


@pytest.fixture
def grpc_rig(impl: ModuleType):
    """Fixture providing an in-process gRPC server on port 0 and a connected client stub."""
    server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=8))
    servicer = impl.KeyValueServicer()
    kv_pb2_grpc.add_KeyValueServiceServicer_to_server(servicer, server)

    port = server.add_insecure_port("127.0.0.1:0")
    server.start()

    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = kv_pb2_grpc.KeyValueServiceStub(channel)

    try:
        yield stub
    finally:
        channel.close()
        server.stop(grace=None)


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_put_and_get(grpc_rig: kv_pb2_grpc.KeyValueServiceStub) -> None:
    put_resp = grpc_rig.Put(kv_pb2.PutRequest(key="user:101", value="Alice"))
    assert put_resp.success

    get_resp = grpc_rig.Get(kv_pb2.GetRequest(key="user:101"))
    assert get_resp.key == "user:101"
    assert get_resp.value == "Alice"


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_missing_key_aborts_not_found(grpc_rig: kv_pb2_grpc.KeyValueServiceStub) -> None:
    # A missing key must abort with StatusCode.NOT_FOUND, NOT return an empty payload
    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_rig.Get(kv_pb2.GetRequest(key="non_existent_key"))

    status_code = exc_info.value.code()
    assert status_code == grpc.StatusCode.NOT_FOUND, (
        f"Expected grpc.StatusCode.NOT_FOUND, got {status_code}. "
        "Do not return an empty GetResponse for missing items; use context.abort(StatusCode.NOT_FOUND, ...)."
    )


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_deadline_exceeded(grpc_rig: kv_pb2_grpc.KeyValueServiceStub) -> None:
    # Key 'slow' sleeps for 0.15s; client timeout is 0.05s
    with pytest.raises(grpc.RpcError) as exc_info:
        grpc_rig.Get(kv_pb2.GetRequest(key="slow"), timeout=0.05)

    assert exc_info.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_concurrent_put_get(grpc_rig: kv_pb2_grpc.KeyValueServiceStub) -> None:
    n_workers = 20

    def worker(i: int) -> str:
        k = f"k_{i}"
        v = f"v_{i}"
        grpc_rig.Put(kv_pb2.PutRequest(key=k, value=v))
        resp = grpc_rig.Get(kv_pb2.GetRequest(key=k))
        return resp.value

    run = run_concurrently(worker, n_threads=n_workers)
    assert not run.errors, f"Concurrent RPC errors: {run.errors}"
    for i in range(n_workers):
        assert run.results[i] == f"v_{i}"
