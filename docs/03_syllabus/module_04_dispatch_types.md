# Module 4 — Dynamic Dispatch, Protocols & Type Systems

**Learning outcomes.**

1. Explain attribute lookup (instance → type MRO → descriptors) as the Python equivalent of vtable dispatch.
2. Choose between `abc.ABC` (nominal) and `typing.Protocol` (structural) for interface boundaries.
3. Write generic, statically checked code (PEP 695 syntax) that passes `mypy --strict`.
4. Implement the core data model protocols (`__eq__`/`__hash__`, `__iter__`, `__len__`, `__enter__`, descriptors) correctly.

---

## (a) Core Mental Model

```text
C++                                         Python
───────────────────────────────────         ─────────────────────────────────────────
class Storage { virtual Get()=0; };         class Storage(ABC):            # nominal
                                                @abstractmethod
                                                def get(self, k: str) -> bytes: ...

template<class T> concept Store =           class Store(Protocol):         # structural
  requires(T t){ t.get(""); };                  def get(self, k: str) -> bytes: ...

obj->vptr->Get(obj)                         type(obj).__mro__ lookup → function
                                            → descriptor __get__ binds self → call
override / final                            @typing.override (3.12) / @typing.final
template<class T> class Box                 class Box[T]: ...              # PEP 695
using Id = StrongTypedef<int>               UserId = NewType("UserId", int)
```

**One-liner:** *Every method call is dynamically dispatched by name at runtime; "concepts" are checked by an external static analyzer, not the compiler — so the type checker is part of your build, not an optional linter.*

## (b) Systems Deep-Dive

### 1. Attribute lookup = dispatch
`obj.attr` → `type(obj).__getattribute__` (default `PyObject_GenericGetAttr`):
1. Look up `attr` along `type(obj).__mro__`. If found and it's a **data descriptor** (`__get__` + `__set__`/`__delete__`, e.g. `property`, slot member) → call it.
2. Else check the instance's `__dict__`/inline values.
3. Else if found in step 1 as a **non-data descriptor** (plain function → bound method) → call `__get__`.
4. Else `__getattr__` fallback, else `AttributeError`.

The type attribute cache (keyed on type version tags) and the 3.11+ specializing interpreter (`LOAD_ATTR_METHOD_WITH_VALUES`, etc.) make this fast in the monomorphic case — conceptually an inline cache, like a JIT's devirtualization guard.

### 2. MRO and cooperative inheritance
- C3 linearization; `super()` follows the MRO of the *instance's* type, not the lexical parent (unlike `Base::method()`).
- Cooperative `__init__(self, **kwargs)` chains for mixins; diamond inheritance resolved deterministically.

### 3. Data model ("operator overloading")
- Dunders map to C slots on the type: `__add__`→`nb_add`, `__getitem__`→`mp_subscript`/`sq_item`, `__hash__`→`tp_hash`, `__iter__`→`tp_iter`.
- Looked up on the **type**, not the instance (assigning `obj.__len__ = …` does nothing for `len(obj)`).
- `NotImplemented` return triggers reflected operations; `functools.total_ordering`.
- `__eq__` defined ⇒ `__hash__ = None` unless explicitly defined.

### 4. Descriptors, properties, and class creation
- `property` ≈ C++ getters/setters with attribute syntax; `functools.cached_property` (instance-dict based → incompatible with `__slots__`).
- `__set_name__`, `__init_subclass__` (plugin registries without metaclasses), metaclasses as last resort.
- Class body executes at import time → decorators and registries are runtime code.

### 5. Nominal vs structural interfaces

| | `abc.ABC` | `typing.Protocol` |
|:---|:---|:---|
| C++ analogue | Abstract base with pure virtuals | C++20 concept |
| Conformance | Inheritance or `ABC.register()` | Shape match (static) |
| Runtime enforcement | Instantiation blocked if abstract methods remain | None, unless `@runtime_checkable` (checks *presence* only, not signatures) |
| Shared implementation | Yes (mixin methods) | Possible but unusual |
| Best for | Framework base classes you own | Boundaries with third-party / generated code (e.g. gRPC stubs) |

### 6. Static typing as a verification layer
- `mypy --strict` / `pyright --strict` in CI; annotations are not enforced at runtime (and are lazily evaluated in 3.14, PEP 649).
- PEP 695 (3.12): `def first[T](xs: Sequence[T]) -> T`, `class Box[T]`, `type Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None`.
- `TypeVar` bounds/constraints ≈ concept constraints; `ParamSpec` for type-preserving decorators; `TypeVarTuple` for variadics; `Self`; `Literal`; `TypedDict`; `NewType` ≈ strong typedef (zero runtime cost); `@overload` ≈ overload set (static only); `@override` catches signature drift like C++ `override`.
- Variance: `list[Derived]` is **not** a `list[Base]` (invariant, mutable), `Sequence[Derived]` is (covariant) — same reasoning as `std::vector<Derived*>` vs `std::span<Base* const>`.
- `typing.cast` is a no-op `static_cast` you promise is valid; `Any` disables checking — treat it like `reinterpret_cast`.

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ | FE |
|:---|:---|:---|
| `Protocol` at module boundaries, concrete classes inside | Deep inheritance trees mirroring C++ hierarchies | — |
| `@dataclass(frozen=True)` for hashable value types | `__eq__` without `__hash__` | — |
| `functools.singledispatch` for open-ended type switches | `if isinstance(x, A) … elif isinstance(x, B)` ladders | — |
| `executor.submit(fn, arg)` / `partial(fn, arg)` | `lambda: fn(arg)` in a loop | FE-9 |
| `@override` on every overriding method | Silent signature drift | — |
| `NewType("OrderId", int)` | Bare `int` everywhere | — |
| Properties only when computation or validation is needed | Java/C++-style `get_x()`/`set_x()` boilerplate | — |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| M4-L01 | Pluggable Storage Backend | `class IStore { virtual ... = 0; }` + factory | `isinstance` ladders, string type tags | `Protocol` boundary; ≥2 backends; `mypy --strict` clean; fake backend in tests without inheritance | `mypy.api.run` in pytest, behavioural tests |
| M4-L02 | Hash/Eq/Ordering Value Type | `operator==`, `operator<=>`, `std::hash` | Mutable class with `__eq__` only | Usable as dict key / in set; total ordering; immutable | Property tests on contract |
| M4-L03 | Type-Preserving Retry Decorator | Variadic template wrapper with perfect forwarding | `def retry(f): def w(*a, **k)` losing signature | `ParamSpec`-typed; `reveal_type` matches original; late-binding bug absent | mypy output assertions |
| M4-L04 | Descriptor-Validated Config | Setter validation in C++ class | Manual `set_port()` methods | `__set_name__`-based descriptor; error messages include field name | Behavioural tests |
| M4-L05 | Plugin Registry | Static registration via global ctor trick | Manual `REGISTRY = {}` edits | `__init_subclass__` registration; import-time order independent | Registry content tests |

### Exit criteria
- All later lab code passes `mypy --strict`.
- Translation note: *"Why `Protocol` is the right type for a gRPC stub dependency in business logic."*
