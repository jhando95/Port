"""Yaz0 compression codec (Nintendo first-party LZ77 variant, e.g. .szs files).

Stream layout: 16-byte header ("Yaz0" magic, u32 BE decompressed size, 8 bytes
reserved), then groups of 8 operations described by a leading code byte, MSB
first. Bit set = one literal byte. Bit clear = back-reference of two bytes
``NR RR``: distance = (R<<8|RR) + 1, count = N + 2 — unless N == 0, in which
case a third byte follows and count = byte + 0x12.
"""

from __future__ import annotations

import struct

MAGIC = b"Yaz0"
MAX_DISTANCE = 0x1000
MIN_MATCH = 3
MAX_MATCH = 0xFF + 0x12  # 273, via the three-byte encoding


def is_yaz0(data: bytes) -> bool:
    return data[:4] == MAGIC


def decompress(data: bytes) -> bytes:
    if not is_yaz0(data):
        raise ValueError("not a Yaz0 stream (bad magic)")
    (out_size,) = struct.unpack(">I", data[4:8])
    out = bytearray()
    pos = 16
    code = 0
    bits_left = 0
    while len(out) < out_size:
        if bits_left == 0:
            code = data[pos]
            pos += 1
            bits_left = 8
        if code & 0x80:
            out.append(data[pos])
            pos += 1
        else:
            b1, b2 = data[pos], data[pos + 1]
            pos += 2
            distance = ((b1 & 0x0F) << 8 | b2) + 1
            count = b1 >> 4
            if count == 0:
                count = data[pos] + 0x12
                pos += 1
            else:
                count += 2
            if distance > len(out):
                raise ValueError("Yaz0 back-reference before start of output")
            for _ in range(count):  # byte-at-a-time: references may overlap
                out.append(out[-distance])
        code <<= 1
        bits_left -= 1
    return bytes(out[:out_size])


def _find_match(data: bytes, pos: int) -> tuple[int, int]:
    """Greedy longest-match search in the trailing window. Returns (distance, length)."""
    best_len = 0
    best_dist = 0
    window_start = max(0, pos - MAX_DISTANCE)
    max_len = min(MAX_MATCH, len(data) - pos)
    if max_len < MIN_MATCH:
        return 0, 0
    search = data[window_start:pos]
    target = data[pos : pos + MIN_MATCH]
    start = 0
    while True:
        idx = search.find(target, start)
        if idx == -1:
            break
        cand = window_start + idx
        # Comparing data[cand + length] handles overlapping matches too: for
        # length >= distance those bytes equal what the decompressor will have
        # just written.
        length = MIN_MATCH
        while length < max_len and data[cand + length] == data[pos + length]:
            length += 1
        if length > best_len:
            best_len = length
            best_dist = pos - cand
            if best_len == max_len:
                break
        start = idx + 1
    if best_len < MIN_MATCH:
        return 0, 0
    return best_dist, best_len


def compress(data: bytes) -> bytes:
    """Greedy Yaz0 compressor. Output is valid Yaz0; ratio is decent, not optimal."""
    out = bytearray()
    out += MAGIC
    out += struct.pack(">I", len(data))
    out += b"\x00" * 8

    pos = 0
    while pos < len(data):
        code = 0
        chunk = bytearray()
        for bit in range(8):
            if pos >= len(data):
                break
            dist, length = _find_match(data, pos)
            if length >= MIN_MATCH:
                if length >= 0x12:
                    chunk.append((dist - 1) >> 8)
                    chunk.append((dist - 1) & 0xFF)
                    chunk.append(length - 0x12)
                else:
                    chunk.append(((length - 2) << 4) | ((dist - 1) >> 8))
                    chunk.append((dist - 1) & 0xFF)
                pos += length
            else:
                code |= 0x80 >> bit
                chunk.append(data[pos])
                pos += 1
        out.append(code)
        out += chunk
    return bytes(out)
