"""M7-L01 · NAIVE translation — unmasked bit shifts and unchecked buffer loops.

DO NOT EDIT: the test-suite must keep failing on this file (see `lab.py verify`).
"""

from __future__ import annotations


def encode_varint(n: int) -> bytes:
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)


def decode_varint(buf: bytes, offset: int = 0) -> tuple[int, int]:
    # Naive bug: uncheck loop raises IndexError on truncated buffers instead of ValueError
    idx = offset
    res = 0
    shift = 0
    while True:
        b = buf[idx]  # Raises IndexError on truncated buffer
        idx += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, idx - offset


def encode_zigzag(n: int, bits: int = 32) -> int:
    # Naive anti-pattern: incorrect zigzag mapping collides positive and negative values
    return (n << 1) if n >= 0 else -(n << 1)


def decode_zigzag(n: int) -> int:
    return (n >> 1) if (n % 2 == 0) else -(n >> 1)
