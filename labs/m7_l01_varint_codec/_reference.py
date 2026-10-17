"""M7-L01 · IDIOMATIC reference (spoiler).

Implements bounds-checked base-128 varint and bitwise zigzag codecs.
"""

from __future__ import annotations


def encode_varint(n: int) -> bytes:
    if n < 0:
        raise ValueError("Varint must be non-negative")
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def decode_varint(buf: bytes, offset: int = 0) -> tuple[int, int]:
    res = 0
    shift = 0
    idx = offset
    buf_len = len(buf)
    while idx < buf_len:
        b = buf[idx]
        idx += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            return res, idx - offset
        shift += 7
        if shift > 70:
            raise ValueError("Varint overflow (exceeds 10 bytes)")
    raise ValueError("Truncated varint buffer (unexpected EOF)")


def encode_zigzag(n: int, bits: int = 32) -> int:
    mask = (1 << bits) - 1
    return ((n << 1) ^ (n >> (bits - 1))) & mask


def decode_zigzag(n: int) -> int:
    return (n >> 1) ^ (-(n & 1))
