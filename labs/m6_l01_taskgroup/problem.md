# M6-L01 · Structured Concurrency with TaskGroup

## Problem

In high-concurrency microservices, fan-out queries (fetching user profiles, inventory, and billing simultaneously)
must execute concurrently. If one backend call fails or times out, the service must cancel all sibling
in-flight calls immediately to conserve resources and avoid zombie work.

Your task is to build `fanout_pipeline(inputs, worker_fn)` using modern Python 3.12+ structured concurrency.

### Required API

| Member | Semantics |
|:---|:---|
| `async def fanout_pipeline(inputs: list[T], worker: Callable[[T], Awaitable[R]]) -> list[R]` | Concurrently executes `worker(x)` for each item in `inputs` and returns results in original index order. |
| Cancellation Invariant | If any worker raises an exception, all in-flight sibling tasks must be cancelled, and no running background tasks may be leaked after `fanout_pipeline` returns. |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), C++20 `std::jthread` and `std::stop_token` enforce structured lifetimes:
a `jthread` automatically joins upon destruction and signals cancellation tokens when aborted.

## The Naive Translation

In [naive.py](./naive.py), a developer transitions to asyncio by firing unstructured tasks:
`task = asyncio.create_task(worker(item))` without tracking their lifetime, or using synchronous
blocking functions (e.g. `time.sleep`) inside coroutines.
When a task fails, sibling tasks are abandoned in the background, continuing to burn CPU and socket connections.

## Your Task

Refactor [solution.py](./solution.py) to use `asyncio.TaskGroup()`.
Ensure that results are collected in original input order, and when an error occurs,
all siblings are cancelled before the exception is propagated.

## Verification

```bash
./lab.py test M6-L01
./lab.py verify M6-L01
```
