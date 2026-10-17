"""M8-L01 · IDIOMATIC reference (spoiler).

Uses `context.abort(grpc.StatusCode.NOT_FOUND, ...)` and synchronizes internal state.
"""

from __future__ import annotations

import threading
import time
import grpc
from labs.m8_l01_grpc_service import kv_pb2, kv_pb2_grpc


class KeyValueServicer(kv_pb2_grpc.KeyValueServiceServicer):
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self._lock = threading.Lock()

    def Put(self, request: kv_pb2.PutRequest, context: grpc.ServicerContext) -> kv_pb2.PutResponse:
        with self._lock:
            self.store[request.key] = request.value
        return kv_pb2.PutResponse(success=True)

    def Get(self, request: kv_pb2.GetRequest, context: grpc.ServicerContext) -> kv_pb2.GetResponse:
        if request.key == "slow":
            time.sleep(0.15)
        with self._lock:
            if request.key not in self.store:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Key {request.key!r} not found in store")
            return kv_pb2.GetResponse(key=request.key, value=self.store[request.key])
