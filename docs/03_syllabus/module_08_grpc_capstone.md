# Module 8 — Capstone: End-to-End gRPC Microservice

**Learning outcomes.**

1. Implement all four RPC shapes (unary, server-streaming, client-streaming, bidirectional) in Python.
2. Build the same service twice — synchronous `grpc.server` on a `ThreadPoolExecutor`, and `grpc.aio` — and explain their concurrency/capacity models.
3. Apply deadlines, cancellation, status codes, metadata, and interceptors as first-class design elements.
4. Test the service in-process with pytest: correctness, concurrency invariants, deadline behaviour, latency budgets, graceful shutdown.

---

## (a) Core Mental Model

```text
Client stub call                         Server
────────────────                          ──────────────────────────────────────────
stub.Get(req, timeout=0.5,               HTTP/2 stream ← one RPC
         metadata=[("x-req-id", id)])     │
  │  serialize (M7)                       ├─ interceptors (auth, logging, metrics)
  ▼                                       ├─ handler(request, context)
HTTP/2 stream on a multiplexed           │     sync:  runs on a ThreadPoolExecutor thread (M5)
TCP connection (channel)                  │     aio:   runs as a coroutine on the event loop (M6)
  ◄──────── response + status + trailers ─┘
Deadline propagates; expiry ⇒ DEADLINE_EXCEEDED on both sides
```

**One-liner:** *A gRPC method is a typed function call across a network with a deadline, a status code, and metadata; on the server it is just a handler running under the concurrency model you chose — so every M5/M6 rule applies to servicer state.*

## (b) Systems Deep-Dive

### 1. Transport and channel
- HTTP/2: one TCP connection, many concurrent streams, flow control windows per stream/connection, HPACK header compression.
- `grpc.Channel` is long-lived, thread-safe, and expensive to create — share one per target. Connection states (IDLE → CONNECTING → READY → TRANSIENT_FAILURE), `grpc.channel_ready_future`.
- Channel options: keepalive (`grpc.keepalive_time_ms`), message size limits, retry policy via `grpc.service_config` JSON.
- **Fork safety:** gRPC's C core runs its own threads; create channels/servers *after* `fork` (or use `spawn`/`forkserver`), see `GRPC_ENABLE_FORK_SUPPORT`.

### 2. The four RPC shapes
| Shape | Proto | Sync handler signature | aio handler |
|:---|:---|:---|:---|
| Unary | `rpc Get(GetReq) returns (GetResp)` | `def Get(self, req, ctx) -> GetResp` | `async def Get(self, req, ctx)` |
| Server streaming | `returns (stream Event)` | generator `yield`s responses | async generator / `await ctx.write()` |
| Client streaming | `(stream PutReq) returns (Summary)` | iterates `request_iterator` | `async for req in request_iterator` |
| Bidi | `(stream A) returns (stream B)` | iterate + yield | async iterate + yield / read/write |

### 3. Sync server capacity model
```python
server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=32),
    interceptors=[AuthInterceptor(), MetricsInterceptor()],
    maximum_concurrent_rpcs=256,          # beyond → RESOURCE_EXHAUSTED
)
```
- **Every in-flight RPC occupies a worker thread for its whole duration.** A long-lived server stream pins a thread; 32 watchers ⇒ unary RPCs starve. Mitigation: bound streams, use aio for streaming-heavy services.
- Servicer state is shared across worker threads ⇒ M5 locking rules apply verbatim.
- GIL: handlers that do CPU work serialize; I/O and (de)serialization inside the C core release the GIL.

### 4. `grpc.aio` server
- `grpc.aio.server()`; `await server.start()`; `await server.wait_for_termination()`; `await server.stop(grace)`.
- One event loop serves thousands of concurrent streams; state between awaits needs no lock, invariants spanning an `await` need `asyncio.Lock` (M6-L06).
- Blocking calls in handlers stall *all* RPCs → `asyncio.to_thread`.

### 5. Status, deadlines, cancellation
- Map domain exceptions (M3-L05) to `grpc.StatusCode` via `context.abort(code, details)` (raises) — `NOT_FOUND`, `ALREADY_EXISTS`, `FAILED_PRECONDITION`, `ABORTED` (optimistic-concurrency conflicts), `RESOURCE_EXHAUSTED`, `UNAVAILABLE` (retryable), `DEADLINE_EXCEEDED`, `INTERNAL`.
- **Always set client deadlines** (`timeout=`). Server reads `context.time_remaining()` and propagates the remaining budget to downstream calls.
- Cancellation: sync — `context.is_active()`, `context.add_callback(cb)`; aio — `CancelledError` delivered into the handler (M6-L05 rules).

### 6. Metadata and interceptors
- Metadata keys are lowercase ASCII; binary values require a `-bin` suffix. Read with `context.invocation_metadata()`; send with `send_initial_metadata`/`set_trailing_metadata`; client gets trailers via `stub.Method.with_call(...)`.
- Server interceptors (`grpc.ServerInterceptor.intercept_service(continuation, handler_call_details)`; `grpc.aio.ServerInterceptor`) for auth, request-id propagation (into a `ContextVar`), logging, metrics. Wrapping the returned `RpcMethodHandler` is required to observe latency/status.
- Client interceptors (`grpc.UnaryUnaryClientInterceptor`, …) for auth injection, retries, tracing.

### 7. Operability
- Health checking (`grpcio-health-checking`), server reflection (`grpcio-reflection`) for `grpcurl`.
- Graceful shutdown: on SIGTERM → mark NOT_SERVING → `server.stop(grace)` lets in-flight RPCs finish, rejects new ones.
- Observability: structured logs keyed by request id; latency histograms; OpenTelemetry instrumentation (awareness).

### 8. Testing strategy (pytest)
- In-process server on an ephemeral port: `port = server.add_insecure_port("127.0.0.1:0")`; session- or module-scoped fixtures yielding a channel/stub; teardown with `server.stop(None)`.
- Layers: (1) pure domain logic unit tests (no gRPC); (2) servicer tests with a real in-process server; (3) concurrency stress with `run_concurrently`; (4) deadline/cancellation tests with deliberately slow handlers; (5) latency budget tests with `measure_latency`.
- aio tests with `pytest-asyncio` (`@pytest.mark.asyncio`, loop-scoped fixtures).

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ |
|:---|:---|
| One shared channel per target, managed with `with`/`async with` | New channel per request |
| `timeout=` on every client call; propagate `time_remaining()` | No deadlines |
| `context.abort(StatusCode.NOT_FOUND, ...)` from a domain-exception mapping interceptor | Returning empty responses to signal errors |
| Locks (sync) / single-owner state (aio) for servicer state | Unprotected dicts in servicers |
| aio server for streaming-heavy services | Sync server with unbounded server-streams |
| `server.stop(grace)` on SIGTERM | `kill -9` / daemon threads |
| Domain ↔ proto converters at the edge (M7-L05) | `_pb2` types throughout business logic |
| Business logic depends on a `Protocol`, not the generated stub (M4) | Hard-wired stubs that make unit tests need a network |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| M8-L01 | Unary KV Service + In-Process Test Rig | gRPC C++ sync server | Global dict servicer, no deadlines, errors as empty responses | Correct status codes; fixture-managed server on port 0; client deadlines | `grpc.RpcError.code()` assertions |
| M8-L02 | Optimistic Concurrency (CAS) | `std::atomic::compare_exchange` on a version | Read-modify-write across RPCs | `Put(key, value, expected_version)` → `ABORTED` on conflict; 200 concurrent clients, zero lost updates | `run_concurrently`, invariant check |
| M8-L03 | Streaming & Thread-Pool Starvation | Async C++ completion-queue server | Server-streaming `Watch` on a 4-thread sync server | Demonstrate starvation, then fix (bounded watchers / aio); unary p99 within budget while 50 watchers are connected | `measure_latency` under load |
| M8-L04 | Interceptors & Metadata | C++ interceptor API | Auth/logging copy-pasted into each handler | Auth interceptor (`UNAUTHENTICATED`), request-id propagation via `ContextVar`, latency metrics per method | Metadata round-trip, metrics assertions |
| M8-L05 | Deadlines & Cancellation | `ClientContext::set_deadline` | Handler ignoring deadline, downstream calls without timeout | Server stops work on cancel; downstream deadline ≤ remaining budget; `DEADLINE_EXCEEDED` within ε | Timing bounds, work counters |
| M8-L06 | Port to `grpc.aio` | Callback API server | Blocking calls inside `async def` handlers | Same test suite passes against aio server; loop lag p99 < 10 ms | Shared parametrized suite, loop-lag sampler |

### Capstone Specification — `kvwatch` Service

```protobuf
syntax = "proto3";
package kvwatch.v1;

service KV {
  rpc Get(GetRequest)              returns (GetResponse);          // unary
  rpc Put(PutRequest)              returns (PutResponse);          // unary, CAS on version
  rpc Watch(WatchRequest)          returns (stream WatchEvent);    // server streaming
  rpc BulkPut(stream PutRequest)   returns (BulkPutSummary);       // client streaming
  rpc Session(stream SessionCmd)   returns (stream SessionReply);  // bidi
}
```

**Non-functional requirements (each backed by a test):**

| Requirement | Verification |
|:---|:---|
| Linearizable `Put` per key with optimistic versions | 200-client CAS stress: final version = successful puts |
| `Watch` delivers every committed change in order per key | Sequence-number gap detection |
| Bounded resources: ≤ N concurrent watchers, bounded per-watcher queue; slow consumers are disconnected with `RESOURCE_EXHAUSTED` | Slow-consumer test |
| Deadlines honoured end-to-end | Slow-backend fault injection |
| Auth via metadata; request id in all logs | Interceptor tests |
| Graceful shutdown drains in-flight RPCs within `grace` | Shutdown-during-load test |
| Identical behaviour on sync and aio implementations | One suite parametrized over both servers |
| Correct on free-threaded CPython (if dependencies available) | CI job on `python3.14t` (allowed to skip if `grpcio` lacks `t` wheels) |
| Latency: unary p99 < 5 ms locally at 200 RPS | `measure_latency` budget |

### Exit criteria
- Capstone suite green on both server implementations.
- Design document (≤2 pages): concurrency model choice, locking strategy, failure-mode table, capacity estimate.
