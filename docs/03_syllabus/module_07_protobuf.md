# Module 7 — Serialization & Protocol Buffers

**Learning outcomes.**

1. Encode and decode the Protobuf wire format by hand (varints, zigzag, tags, length-delimited fields).
2. Design `.proto` schemas that evolve safely (field numbers, `reserved`, presence, enums, `oneof`).
3. Generate Python code (`grpc_tools.protoc` with `.pyi` stubs) and use the generated API idiomatically.
4. Quantify the size/CPU trade-offs of JSON vs Protobuf vs hand-rolled `struct` encoding.

---

## (a) Core Mental Model

```text
C/C++ habit                                   Protobuf reality
──────────────────────────────────            ──────────────────────────────────────────
fwrite(&s, sizeof s, 1, f)                    Self-describing-ish TLV stream:
  - layout = compiler + ABI + endianness        [tag=(field_no<<3)|wire_type][payload]...
  - any field change breaks readers           Unknown fields are skipped (and preserved)
#pragma pack + htonl()                        Varints: small numbers → few bytes
Version byte + manual migration code          Evolution by field NUMBER, never by name/order
```

**One-liner:** *A Protobuf message is a sequence of `(field number, wire type, payload)` records; the schema is a contract on field numbers, so compatibility is a property of how you change numbers, not code.*

## (b) Systems Deep-Dive

### 1. Wire format (encoding spec)
| Wire type | Id | Used for |
|:---|:---|:---|
| VARINT | 0 | `int32`, `int64`, `uint32`, `uint64`, `sint32`, `sint64`, `bool`, `enum` |
| I64 | 1 | `fixed64`, `sfixed64`, `double` |
| LEN | 2 | `string`, `bytes`, embedded messages, packed repeated scalars |
| SGROUP/EGROUP | 3/4 | Deprecated groups |
| I32 | 5 | `fixed32`, `sfixed32`, `float` |

- **Varint:** base-128, little-endian groups of 7 bits, MSB = continuation. `300` → `AC 02`.
- **Negative `int32`/`int64`** are sign-extended to 64 bits → always **10 bytes**. Use `sint32`/`sint64` (**zigzag**: `(n << 1) ^ (n >> 63)`) for frequently negative values.
- **Tag** = `(field_number << 3) | wire_type`; field numbers 1–15 fit in a one-byte tag → reserve them for hot fields. Max field number 2²⁹−1; 19000–19999 reserved.
- Repeated scalars are **packed** by default in proto3 (one LEN record).
- Last-one-wins for repeated occurrences of a non-repeated field; embedded messages **merge**.
- Map fields are sugar for `repeated MapEntry { key = 1; value = 2; }`.

### 2. Schema design and evolution
- Safe: add fields (new numbers), remove fields (and `reserved` both number and name), rename fields (binary-compatible; breaks JSON/text formats).
- Unsafe: change a field's number, change wire-incompatible types (`int32` ↔ `string`), reuse a number.
- **Presence:** proto3 scalars without `optional` cannot distinguish "unset" from zero; use `optional` (generates `HasField`) or wrapper types. Messages always have presence.
- Enums: first value must be 0 (`FOO_UNSPECIFIED = 0`); proto3 enums are open (unknown values preserved as ints).
- `oneof` for tagged unions (≈ `std::variant`); `WhichOneof("field")`.
- Well-known types: `Timestamp`, `Duration`, `Empty`, `FieldMask`, `Struct`, `Any`.
- Protobuf **Editions** (`edition = "2023"`) generalize proto2/proto3 into per-feature settings — awareness level only.

### 3. Python code generation and runtime
```bash
python -m grpc_tools.protoc -I proto \
  --python_out=gen --pyi_out=gen --grpc_python_out=gen proto/kv.proto
```
- Generated `_pb2.py` registers descriptors into a `DescriptorPool`; message classes are built at import time. `_pb2.pyi` gives mypy/pyright full types.
- Backend: **upb** (C) since protobuf 4.21 — check `google.protobuf.internal.api_implementation.Type()`. Parsing/serialization runs in C; field access crosses the C boundary each time.
- Gotchas: composite fields can't be assigned (`msg.sub = other` → error; use `msg.sub.CopyFrom(other)`); repeated fields use `.append`/`.extend`/`.add()`; reading an unset submessage returns a default instance *without* setting it (until you write to it); `ClearField`, `HasField`, `ListFields`.
- `json_format.MessageToJson` (int64 serialized as strings; field names camelCased by default).
- Generated import paths: `protoc` emits absolute imports (`import kv_pb2`); place output on `sys.path` or post-process — a classic packaging pitfall.

### 4. Cost model
- JSON: text, field names repeated per record, float formatting/parsing, no schema.
- Protobuf: smaller (varints, numeric tags), schema-checked, C-accelerated parse — but Python object construction per message still dominates for small messages.
- `struct`: smallest and fastest for fixed layouts, zero evolvability.
- Measure: bytes on wire, encode/decode µs per message (p50/p99), allocations per message.

## (c) Key Idioms & Gotchas

| Idiom ✅ | Anti-pattern ❌ |
|:---|:---|
| `reserved 4; reserved "old_name";` when removing fields | Deleting a field and later reusing its number |
| `sint64` for signed deltas | `int64` for values that are often negative |
| `optional` for scalars whose absence is meaningful | Using `0`/`""` as "not set" sentinel |
| `msg.sub.CopyFrom(other)` | `msg.sub = other` |
| `ENUM_UNSPECIFIED = 0` | Meaningful value at 0 |
| Generate `.pyi` and type-check handlers | Untyped `Any` messages flowing through business logic |
| Convert at the boundary to domain dataclasses | Passing `_pb2` messages through every layer |

## (d) Interactive Lab Specification

| ID | Title | C++ anchor | Naive Python | Refactor criteria | Probes |
|:---|:---|:---|:---|:---|:---|
| M7-L01 | Hand-Rolled Varint & Zigzag Codec | `uint8_t*` cursor + bit shifts | `str`-based bit manipulation, unmasked negatives (FE-7) | Bit-exact vs `protobuf` library for random inputs; negative `int32` → 10 bytes; decoder rejects truncated input | Hypothesis round-trip vs library oracle |
| M7-L02 | Schema Design & Codegen | Versioned C struct headers | Single `bytes` blob field with JSON inside | Typed schema with `oneof`, `optional`, WKTs; `.pyi` generated; `mypy --strict` on handlers | protoc invocation in fixture, mypy API |
| M7-L03 | Schema Evolution Matrix | ABI compatibility checks | Renumbered fields across versions | v1↔v2 forward/backward compatibility tests pass; unknown fields preserved through a v1 relay | Cross-version encode/decode matrix |
| M7-L04 | Serialization Cost Benchmark | `memcpy` struct vs text | Measuring once with `time.time()` | Reproducible benchmark (warm-up, p50/p99, bytes, allocations) for JSON/Protobuf/`struct`; written trade-off analysis | `measure_latency`, `measure_alloc` |
| M7-L05 | Domain Boundary Mapping | DTO ↔ domain object converters | `_pb2` messages used as domain models | Pure converters with round-trip property tests; domain layer has zero protobuf imports | Import-graph check, Hypothesis |

### Exit criteria
- Can decode a hex dump of a small message by hand.
- Translation note: *"Why Protobuf compatibility is about numbers, and how that compares to C++ ABI compatibility."*
