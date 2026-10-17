# Stage 2 Prompt Cookbook & Execution Guide

This document preserves the standardized, plug-and-play prompt template and sequencing strategy for generating and extending modules in **Stage 2** of `cpp2py-systems-lab`.

---

## 1. The Reusable Stage 2 Prompt Template

When running Stage 2 prompts with an LLM (such as Claude Sonnet 3.5/3.7/Opus or Gemini 1.5/2.0/Pro), copy-paste this prompt block, slotting in the module number, title, and focal concepts:

```text
Role: Principal Systems Engineer & Interactive Curriculum Author.
Audience: C/C++ developer transitioning to modern Python 3.12+, targeting production multithreading and gRPC microservices.
Target Module: Module [INSERT NUMBER]: [INSERT MODULE TITLE]

Prerequisites Context:
The learner understands low-level systems mechanics (pointers, manual memory buffers, vtables, compilation units, RAII), but did NOT implement concurrency/multithreading in C/C++. Avoid basic programming 101 explanations; anchor every explanation in runtime mechanics, memory layout, and idiomatic paradigm shifts.

Task:
Generate the complete, unabridged instructional text and interactive, test-driven coding lab for this module. Follow the comparative lab model inspired by 'sql-ra-lab' (side-by-side mental model translation, AST/runtime verification, and automated test harnesses).

Deliverables Required:

1. Systems Deep-Dive & Mechanical Translation:
   - Detail what happens under the hood in CPython for this topic compared to compiled C/C++ behavior (e.g., stack frames vs. PyFrameObject, pointer indirection, cache locality, GIL interaction, or syscall behavior).
   - Address the specific false equivalence or common anti-pattern relevant to this module.

2. Side-by-Side Translation Matrix (3 Concrete Code Studies):
   Provide three distinct real-world patterns illustrating:
   - Column A: The canonical C++ idiom or baseline design.
   - Column B: The naive, C-style Python anti-pattern (what a C++ dev instinctively writes; explain why it fails, leaks, or bottlenecks).
   - Column C: The idiomatic Python 3.12+ solution (leveraging language protocols, standard library features, or zero-cost patterns).

3. Interactive Lab: Test-Driven Pytest Sandbox:
   Provide an end-to-end, runnable interactive lab structured as the canonical harness files:
   - `lab.toml`: Manifest with criteria and naive_must_fail flags.
   - `problem.md`: Problem specification and diagnostic hints.
   - `reference.cpp`: Modern C++ reference implementation.
   - `naive.py`: Naive translation that fails runtime property checks.
   - `solution.py`: Student workspace (seeded from naive.py).
   - `_reference.py`: Idiomatic Python 3.12+ reference oracle.
   - `test_lab.py`: Robust pytest harness using `harness.probes` (validating refcounts, memory allocations, race conditions, or deadlines).

4. Self-Review & Verification Checklist:
   - Provide 3–5 rapid-fire terminal commands to execute the verification (e.g., `./lab.py test <LAB_ID>`, `./lab.py verify <LAB_ID>`) along with an explanation of what the pass/fail output reveals about the underlying runtime.
```

---

## 2. Technical Focus Sequence per Module

When executing Stage 2 for each module, ensure the prompt is injected with the specific runtime mechanics:

| Module | Core Concepts & Systems Focus | Specific Runtime Probes to Emphasize |
|:---|:---|:---|
| **Module 1** | `sys.getrefcount`, `gc.collect()`, cyclic reference traps, `PyObject` header inspection, immortal objects. | `gc_disabled()`, `refcount_delta()`, `is_immortal()` |
| **Module 2** | `sys.getsizeof()`, cache misses with pointer arrays vs. `array.array` / contiguous buffers, `__slots__` memory layout. | `measure_alloc()`, `memoryview.format`, `hasattr(o, '__dict__')` |
| **Module 3** | Replacing RAII destructors (`~T`) with `__enter__` / `__exit__`, exception suppression semantics, `contextlib.ExitStack`. | File descriptor inspection (`/proc/self/fd`), `gc_disabled()`, exception chains |
| **Module 4** | Compile-time templates vs. `typing.Protocol`, structural subtyping vs. nominal inheritance, zero-overhead static checking (`mypy --strict`). | `isinstance(o, Protocol)`, `runtime_checkable`, static mypy verification |
| **Module 5** | Non-concurrency veterans: threads as shared-memory execution units, reproducible race conditions, GIL switch intervals (`sys.setswitchinterval(1e-6)`), I/O syscall releases. | `aggressive_switching()`, `run_concurrently()`, `Barrier` stampedes |
| **Module 6** | Event loop mechanics (`epoll`/`kqueue` under the hood), task scheduling, cooperative yields (`await`), `TaskGroup` cancellation. | `asyncio.TaskGroup()`, `asyncio.timeout()`, event loop lag probes |
| **Module 7** | `.proto` schemas, compiling with `grpc_tools.protoc`, benchmarking binary serialization overhead vs. naive string/JSON formats. | `measure_latency()`, wire-format byte count, varint/zigzag codecs |
| **Module 8** | End-to-end async gRPC service stubs, implementing unary and streaming RPC methods, in-process `grpc.aio` test server and client fixtures. | Port 0 ephemeral servers, deadline propagation, client cancellation |

---

## 3. Automation via `lab.py scaffold`

The CLI tool `./lab.py` includes built-in scaffolding to instantly initialize any Stage 2 lab directory according to this exact specification:

```bash
./lab.py scaffold <MODULE_NUM> <SLUG> "<TITLE>"
```

For example:
```bash
./lab.py scaffold 3 m3_l01_connection_lifecycle "Deterministic Connection Release"
```
This automatically sets up all required triptych files, wired into the scorecard plugin.
