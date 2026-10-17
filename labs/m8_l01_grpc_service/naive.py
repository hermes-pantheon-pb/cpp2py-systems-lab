"""M8-L01 · NAIVE translation — returns empty responses instead of aborting with status codes.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations

import time
import grpc
from labs.m8_l01_grpc_service import kv_pb2, kv_pb2_grpc


class KeyValueServicer(kv_pb2_grpc.KeyValueServiceServicer):
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def Put(self, request: kv_pb2.PutRequest, context: grpc.ServicerContext) -> kv_pb2.PutResponse:
        self.store[request.key] = request.value
        return kv_pb2.PutResponse(success=True)

    def Get(self, request: kv_pb2.GetRequest, context: grpc.ServicerContext) -> kv_pb2.GetResponse:
        if request.key == "slow":
            time.sleep(0.15)
        # Naive anti-pattern: returns empty value instead of aborting with StatusCode.NOT_FOUND
        if request.key not in self.store:
            return kv_pb2.GetResponse(key=request.key, value="")
        return kv_pb2.GetResponse(key=request.key, value=self.store[request.key])
