"""M7-L01 · Verification harness for binary varint and zigzag wire codecs.

Run:  ./lab.py test M7-L01 [--target naive|solution|reference]
"""

from __future__ import annotations

from types import ModuleType

import pytest


# --------------------------------------------------------------------------- C1
@pytest.mark.criterion("C1")
def test_varint_roundtrip(impl: ModuleType) -> None:
    test_values = [0, 1, 127, 128, 300, 16384, 1_000_000, 2**32 - 1]
    for val in test_values:
        encoded = impl.encode_varint(val)
        decoded, consumed = impl.decode_varint(encoded)
        assert decoded == val, f"Decoded {decoded} != original {val}"
        assert consumed == len(encoded)


# --------------------------------------------------------------------------- C2
@pytest.mark.criterion("C2")
def test_compact_wire_format(impl: ModuleType) -> None:
    # 0 fits in 1 byte: 0x00
    assert impl.encode_varint(0) == b"\x00"
    # 127 fits in 1 byte: 0x7f
    assert impl.encode_varint(127) == b"\x7f"
    # 300 fits in 2 bytes: 300 = 0b100101100 -> [0xAC, 0x02]
    encoded_300 = impl.encode_varint(300)
    assert encoded_300 == b"\xac\x02", f"Expected b'\\xac\\x02', got {encoded_300!r}"


# --------------------------------------------------------------------------- C3
@pytest.mark.criterion("C3")
def test_zigzag_signed_mapping(impl: ModuleType) -> None:
    # Standard Protobuf zigzag mapping
    expected_pairs = [
        (0, 0),
        (-1, 1),
        (1, 2),
        (-2, 3),
        (2, 4),
        (-3, 5),
        (1000, 2000),
        (-1000, 1999),
    ]
    for signed_val, expected_unsigned in expected_pairs:
        actual_unsigned = impl.encode_zigzag(signed_val)
        assert actual_unsigned == expected_unsigned, (
            f"encode_zigzag({signed_val}) = {actual_unsigned} (expected {expected_unsigned}). "
            "Negative numbers must map to odd integers without sign collision!"
        )
        decoded_signed = impl.decode_zigzag(actual_unsigned)
        assert decoded_signed == signed_val, (
            f"decode_zigzag({actual_unsigned}) = {decoded_signed} (expected {signed_val})"
        )


# --------------------------------------------------------------------------- C4
@pytest.mark.criterion("C4")
def test_truncated_buffer_raises_value_error(impl: ModuleType) -> None:
    # Buffer has continuation bit (0x80) set, but no following bytes!
    truncated_buf = b"\x80"
    with pytest.raises(ValueError):
        impl.decode_varint(truncated_buf)

    truncated_300 = b"\xac"  # Missing second byte (0x02)
    with pytest.raises(ValueError):
        impl.decode_varint(truncated_300)
