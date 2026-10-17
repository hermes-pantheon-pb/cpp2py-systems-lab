# M7-L01 · Varint & Zigzag Binary Codec

## Problem

Protocol Buffers achieve compact wire representations by encoding integers as base-128 **Varints**
and signed integers using **Zigzag** encoding.
In this lab, you will implement the core Protobuf wire-format encoder and decoder from scratch.

### Required API

| Member | Semantics |
|:---|:---|
| `encode_varint(n: int) -> bytes` | Encodes non-negative integer into base-128 varint |
| `decode_varint(buf: bytes, offset: int = 0) -> tuple[int, int]` | Decodes varint; returns `(value, bytes_consumed)` |
| `encode_zigzag(n: int, bits: int = 32) -> int` | Maps signed int to unsigned int (`0 ➔ 0`, `-1 ➔ 1`, `1 ➔ 2`, `-2 ➔ 3`) |
| `decode_zigzag(n: int) -> int` | Inverts zigzag mapping |

## The C++ Mental Model

In [reference.cpp](./reference.cpp), C++ implements varint encoding using pointer cursor manipulation
and fixed-width unsigned integers (`uint32_t`, `uint64_t`).

## The Naive Translation

In [naive.py](./naive.py), a developer attempts to write bitwise shifts without accounting for Python's
arbitrary-precision integer model ([FE-7](file:///home/user1/Projects/antigravity-test/cpp2py-systems-lab/docs/02_false_equivalences.md#fe-7)):
In C++, `int32_t n = -1; (n << 1) ^ (n >> 31)` evaluates to `1`.
In Python, integers have infinite sign extension: `-1 >> 31` evaluates to `-1` (all ones), so
`(-1 << 1) ^ (-1 >> 31)` yields `-2 ^ -1 == 1`... BUT for other negative numbers like `-2`,
unmasked arithmetic produces negative numbers or incorrect bit patterns!
Furthermore, `naive.py` hangs or enters an infinite loop when decoding a truncated buffer with the MSB set.

## Your Task

Refactor [solution.py](./solution.py) to implement robust, bounds-checked varint and zigzag codecs.

## Verification

```bash
./lab.py test M7-L01
./lab.py verify M7-L01
```
