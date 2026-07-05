import struct

import pytest

from gcport import yaz0


def test_roundtrip_text():
    data = b"the quick brown fox jumps over the lazy dog " * 50
    compressed = yaz0.compress(data)
    assert yaz0.is_yaz0(compressed)
    assert len(compressed) < len(data)  # highly repetitive input must shrink
    assert yaz0.decompress(compressed) == data


def test_roundtrip_incompressible():
    # pseudo-random but deterministic bytes; no repeated 3-grams likely
    data = bytes((i * 197 + (i >> 3) * 31) & 0xFF for i in range(4096))
    assert yaz0.decompress(yaz0.compress(data)) == data


def test_roundtrip_empty_and_tiny():
    for data in (b"", b"a", b"ab", b"abc", b"\x00" * 3):
        assert yaz0.decompress(yaz0.compress(data)) == data


def test_roundtrip_overlapping_run():
    # long single-byte run forces overlapping back-references
    data = b"\xAB" * 10_000
    compressed = yaz0.compress(data)
    assert len(compressed) < 200
    assert yaz0.decompress(compressed) == data


def test_decompress_known_stream():
    # Hand-built stream: literals "abc", then back-reference dist=3 len=6
    # (overlapping copy) producing "abcabcabc".
    header = b"Yaz0" + struct.pack(">I", 9) + b"\x00" * 8
    # code byte: 1110_0000 -> three literals then a reference
    body = bytes([0b1110_0000]) + b"abc" + bytes([(6 - 2) << 4 | 0x00, 0x02])
    assert yaz0.decompress(header + body) == b"abcabcabc"


def test_decompress_three_byte_reference():
    # literal "x", then dist=1 count=0x12+0x20 using the three-byte form
    count = 0x12 + 0x20
    header = b"Yaz0" + struct.pack(">I", 1 + count) + b"\x00" * 8
    body = bytes([0b1000_0000]) + b"x" + bytes([0x00, 0x00, 0x20])
    assert yaz0.decompress(header + body) == b"x" * (1 + count)


def test_bad_magic_rejected():
    with pytest.raises(ValueError):
        yaz0.decompress(b"Yay0" + b"\x00" * 12)


def test_reference_before_start_rejected():
    header = b"Yaz0" + struct.pack(">I", 4) + b"\x00" * 8
    body = bytes([0b0000_0000, 0x10, 0xFF])  # dist far beyond output start
    with pytest.raises(ValueError):
        yaz0.decompress(header + body)
