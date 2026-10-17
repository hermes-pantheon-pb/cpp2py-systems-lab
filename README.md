# cpp2py-systems-lab 🚀

> An interactive, systems-oriented training curriculum designed for **C/C++ developers transitioning to modern Python 3.12+**, culminating in production-grade multi-threaded services and gRPC microservices.

![Python](https://img.shields.io/badge/Python-3.12%2B%20%7C%203.13-blue.svg)
![Target](https://img.shields.io/badge/Audience-C%2FC%2B%2B%20Systems%20Engineers-orange.svg)
![Status](https://img.shields.io/badge/Framework-Executable%20Triptych%20Harness-emerald.svg)

---

## 🎯 Target Audience & Learning Philosophy

This curriculum treats you as an experienced systems programmer:
- **We skip elementary syntax:** No loops, basic branching, or primitive definition tutorials.
- **We systematically cross-compile your mental model:** Memory layouts, cache locality, pointer indirection, RAII vs deterministic destruction, dynamic dispatch, and the CPython runtime (`PyObject`, pymalloc, eval breaker, GIL).
- **We teach concurrency from first principles:** For developers without prior multi-threading experience in C/C++, building up from threads, preemption, and critical sections to condition variables, single-flight caching, and event-driven async I/O.
- **Side-by-Side Triptych verification (inspired by `sql-ra-lab`):**
  $$\text{C++ Idiom} \longrightarrow \text{Naive C-Style Python Anti-Pattern} \longrightarrow \text{Idiomatic Python 3.12+}$$

---

## 📚 Curriculum Structure (8 Modules)

| # | Module | Core Systems Concept | Stage 1 & 2 Exemplar Lab |
|:---|:---|:---|:---|
| **1** | [The CPython Runtime & Memory Model](docs/03_syllabus/module_01_runtime_memory.md) | `PyObject` header, non-atomic refcounting, generational cyclic GC, ownership graphs | `M1-L01` Ownership Cycles ✅ |
| **2** | [Memory Layout & Core Containers](docs/03_syllabus/module_02_layout_containers.md) | `std::vector` vs pointer arrays, dict open addressing & probing, `__slots__` layout optimization | `M2-L01` Struct Layout & Footprint ✅ |
| **3** | [Resource Management & Lifecycles](docs/03_syllabus/module_03_resources_lifecycles.md) | RAII destructors vs Context Managers, `__enter__`/`__exit__`, `ExitStack` scope guards, domain exceptions | `M3-L01` Deterministic Connection Release ✅ |
| **4** | [Dynamic Dispatch, Protocols & Types](docs/03_syllabus/module_04_dispatch_types.md) | Vtables vs MRO attribute lookup, `abc.ABC` vs `typing.Protocol` (C++ concepts), static typing with Mypy | `M4-L01` Pluggable Storage Protocol ✅ |
| **5** | [Concurrency & The Python Threading Model](docs/03_syllabus/module_05_concurrency_threading.md) | First principles: threads, critical sections, condition variables, GIL dissection, single-flight caching | `M5-L01` Single-Flight Cache ✅ |
| **6** | [Async I/O & Event-Driven Architecture](docs/03_syllabus/module_06_asyncio.md) | OS readiness (`epoll`), event loops, stackless coroutines, structured concurrency (`TaskGroup`) | `M6-L01` Structured Concurrency with TaskGroup ✅ |
| **7** | [Serialization & Protocol Buffers](docs/03_syllabus/module_07_protobuf.md) | Binary wire formats (varint/zigzag/tags), schema evolution rules, `protoc` code generation, cost model | `M7-L01` Varint & Zigzag Binary Codec ✅ |
| **8** | [Capstone Service: gRPC Microservices](docs/03_syllabus/module_08_grpc_capstone.md) | Unary & streaming RPCs, sync ThreadPool vs `grpc.aio`, deadlines, interceptors, in-process test rigs | `M8-L01` In-Process gRPC Service & Deadlines ✅ |

---

## 🛠️ The Interactive Lab Framework

Every lab lives under `labs/<lab_id_slug>/` with an executable triptych:
- `reference.cpp`: Modern C++ reference implementation (mental anchor).
- `naive.py`: Literal translation written with a C++ mindset (broken anti-pattern; fails test harness).
- `solution.py`: Student workspace (starts as a copy of `naive.py`).
- `_reference.py`: Production-grade idiomatic Python 3.12+ implementation (oracle).
- `test_lab.py`: Test suite validating criteria using runtime probes (`gc_disabled`, `refcount_delta`, `measure_alloc`, `aggressive_switching`, `run_concurrently`).

### CLI Commands (`./lab.py`)

```bash
# 1. List all curriculum modules and lab instances
./lab.py list

# 2. Inspect a specific lab, its problem description, and criteria
./lab.py show M1-L01

# 3. Test your active solution
./lab.py test M1-L01

# 4. Run tests against the naive anti-pattern or reference implementation
./lab.py test M1-L01 --target naive
./lab.py test M1-L01 --target reference

# 5. Inspect code diffs
./lab.py diff M1-L01                 # naive.py vs solution.py
./lab.py diff M1-L01 --with-reference # solution.py vs _reference.py

# 6. Meta-verification (verifies reference passes 100% and naive fails required criteria)
./lab.py verify M1-L01
./lab.py verify M2-L01
./lab.py verify M5-L01

# 7. Reset solution workspace
./lab.py reset M1-L01
```

---

## 📖 Key Documentation Deliverables

1. [Comparative Mental-Model Translation Matrix](docs/01_translation_matrix.md)
   - Deep-dive into `PyObject`, name binding vs copying, pointer indirection costs, and the GIL.
2. [The 10 Critical False Equivalences](docs/02_false_equivalences.md)
   - The top 10 subtle traps where C++ developers write buggy or inefficient Python (FE-1 through FE-10).
3. [8-Module Syllabus Architecture](docs/03_syllabus/00_overview.md)
   - Detailed modules 1 through 8 with learning outcomes, systems deep-dives, idioms, and lab specs.
4. [Interactive Lab Harness Specification](docs/04_lab_harness_spec.md)
   - Architecture of the triptych harness, runtime probes library, scorecard plugin, and Stage 2 authoring guide.
