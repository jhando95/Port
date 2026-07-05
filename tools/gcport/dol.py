"""DOL executable format (GameCube/Wii main executable).

Layout: 0x100-byte header, all fields big-endian u32.
  0x00  text section file offsets  [7]
  0x1C  data section file offsets  [11]
  0x48  text section load addresses[7]
  0x64  data section load addresses[11]
  0x90  text section sizes         [7]
  0xAC  data section sizes         [11]
  0xD8  BSS address
  0xDC  BSS size
  0xE0  entry point
A section slot is unused when its offset, address, and size are all zero.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

HEADER_SIZE = 0x100
NUM_TEXT = 7
NUM_DATA = 11


@dataclass
class DolSection:
    kind: str  # "text" or "data"
    index: int
    file_offset: int
    load_address: int
    size: int

    @property
    def name(self) -> str:
        return f".{self.kind}{self.index}"


@dataclass
class Dol:
    sections: list[DolSection] = field(default_factory=list)
    bss_address: int = 0
    bss_size: int = 0
    entry_point: int = 0

    @classmethod
    def parse(cls, data: bytes) -> "Dol":
        if len(data) < HEADER_SIZE:
            raise ValueError(f"DOL too small: {len(data)} bytes")
        words = struct.unpack(">64I", data[:HEADER_SIZE])
        offsets = words[0:18]
        addresses = words[18:36]
        sizes = words[36:54]
        bss_address, bss_size, entry_point = words[54:57]

        sections: list[DolSection] = []
        for i in range(NUM_TEXT + NUM_DATA):
            off, addr, size = offsets[i], addresses[i], sizes[i]
            if off == 0 and addr == 0 and size == 0:
                continue
            kind = "text" if i < NUM_TEXT else "data"
            index = i if i < NUM_TEXT else i - NUM_TEXT
            if off + size > len(data):
                raise ValueError(
                    f".{kind}{index} extends past end of file "
                    f"(offset {off:#x} + size {size:#x} > {len(data):#x})"
                )
            sections.append(DolSection(kind, index, off, addr, size))
        return cls(sections, bss_address, bss_size, entry_point)

    def section_data(self, data: bytes, section: DolSection) -> bytes:
        return data[section.file_offset : section.file_offset + section.size]

    @property
    def file_size(self) -> int:
        """Size of the DOL on disk, computed from its sections."""
        end = HEADER_SIZE
        for s in self.sections:
            end = max(end, s.file_offset + s.size)
        return end

    def describe(self) -> str:
        lines = [
            f"entry point : {self.entry_point:#010x}",
            f"BSS         : {self.bss_address:#010x} ({self.bss_size:#x} bytes)",
            f"file size   : {self.file_size:#x} bytes",
            "sections:",
        ]
        for s in self.sections:
            lines.append(
                f"  {s.name:<7} file {s.file_offset:#08x}  "
                f"load {s.load_address:#010x}  size {s.size:#x}"
            )
        return "\n".join(lines)


def build(sections: list[DolSection], bss_address: int, bss_size: int,
          entry_point: int, payloads: dict[str, bytes]) -> bytes:
    """Build a DOL image from sections and per-section payloads (keyed by name).

    Used for tests and, later, for repacking patched executables.
    """
    offsets = [0] * 18
    addresses = [0] * 18
    sizes = [0] * 18
    end = max([HEADER_SIZE] + [s.file_offset + s.size for s in sections])
    image = bytearray(end)
    for s in sections:
        slot = s.index if s.kind == "text" else NUM_TEXT + s.index
        offsets[slot] = s.file_offset
        addresses[slot] = s.load_address
        sizes[slot] = s.size
        payload = payloads[s.name]
        if len(payload) != s.size:
            raise ValueError(f"{s.name}: payload {len(payload)} != size {s.size}")
        image[s.file_offset : s.file_offset + s.size] = payload
    header = struct.pack(
        ">64I", *offsets, *addresses, *sizes, bss_address, bss_size,
        entry_point, *([0] * 7)
    )
    image[:HEADER_SIZE] = header
    return bytes(image)
