"""GCM/ISO GameCube disc image format: inspect, extract, rebuild.

Disc layout (offsets from start of image):
  0x0000  boot header (0x440 bytes):
            0x000  game ID (4 chars: console, code x2, region)
            0x004  maker code (2 chars)
            0x006  disc number, 0x007 version
            0x01C  DVD magic 0xC2339F3D
            0x020  game name (0x3E0 bytes, NUL padded)
            0x420  main.dol offset
            0x424  FST offset, 0x428 FST size, 0x42C max FST size
  0x0440  bi2.bin (0x2000 bytes)
  0x2440  apploader: 0x10-byte date, entry/size/trailer u32s, then code
  ......  main.dol, FST, file data (positions given by the header/FST)

FST: contiguous 12-byte entries followed by a string table.
  entry[0] is the root directory; its "next" field holds the entry count.
  byte 0        flags (0 = file, 1 = directory)
  bytes 1..3    name offset into string table (u24 BE)
  bytes 4..7    file: data offset       dir: parent entry index
  bytes 8..11   file: data length       dir: index one past the subtree
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DVD_MAGIC = 0xC2339F3D
BOOT_SIZE = 0x440
BI2_SIZE = 0x2000
APPLOADER_OFFSET = 0x2440


@dataclass
class FstFile:
    path: str  # posix path relative to filesystem root
    offset: int
    size: int


@dataclass
class DiscHeader:
    game_id: str
    maker_code: str
    disc_number: int
    version: int
    game_name: str
    dol_offset: int
    fst_offset: int
    fst_size: int
    fst_max_size: int

    @classmethod
    def parse(cls, data: bytes) -> "DiscHeader":
        if len(data) < BOOT_SIZE:
            raise ValueError("image too small for boot header")
        (magic,) = struct.unpack(">I", data[0x1C:0x20])
        if magic != DVD_MAGIC:
            raise ValueError(
                f"bad DVD magic {magic:#010x} (expected {DVD_MAGIC:#010x}) — "
                "not a GameCube disc image?"
            )
        dol_offset, fst_offset, fst_size, fst_max_size = struct.unpack(
            ">4I", data[0x420:0x430]
        )
        return cls(
            game_id=data[0x00:0x04].decode("ascii", "replace"),
            maker_code=data[0x04:0x06].decode("ascii", "replace"),
            disc_number=data[0x06],
            version=data[0x07],
            game_name=data[0x20:0x400].split(b"\x00", 1)[0].decode("ascii", "replace"),
            dol_offset=dol_offset,
            fst_offset=fst_offset,
            fst_size=fst_size,
            fst_max_size=fst_max_size,
        )


def parse_fst(fst: bytes) -> list[FstFile]:
    """Flatten an FST blob into a list of files with full paths."""
    if len(fst) < 12:
        raise ValueError("FST too small")
    num_entries = struct.unpack(">I", fst[8:12])[0]
    if num_entries * 12 > len(fst):
        raise ValueError("FST entry count exceeds FST size")
    string_table = fst[num_entries * 12 :]

    def entry(i: int) -> tuple[int, int, int, int]:
        base = i * 12
        flags_name, a, b = struct.unpack(">III", fst[base : base + 12])
        return flags_name >> 24, flags_name & 0xFFFFFF, a, b

    def name_of(name_off: int) -> str:
        end = string_table.index(b"\x00", name_off)
        return string_table[name_off:end].decode("shift-jis", "replace")

    files: list[FstFile] = []
    # (dir_end, path_prefix) stack; root spans the whole table with empty prefix
    stack: list[tuple[int, str]] = [(num_entries, "")]
    i = 1
    while i < num_entries:
        while i >= stack[-1][0]:
            stack.pop()
        flags, name_off, a, b = entry(i)
        name = name_of(name_off)
        prefix = stack[-1][1]
        if flags & 1:
            stack.append((b, f"{prefix}{name}/"))
        else:
            files.append(FstFile(path=f"{prefix}{name}", offset=a, size=b))
        i += 1
    return files


@dataclass
class DiscImage:
    header: DiscHeader
    files: list[FstFile] = field(default_factory=list)

    @classmethod
    def parse(cls, data: bytes) -> "DiscImage":
        header = DiscHeader.parse(data)
        fst = data[header.fst_offset : header.fst_offset + header.fst_size]
        return cls(header=header, files=parse_fst(fst))

    def describe(self) -> str:
        h = self.header
        total = sum(f.size for f in self.files)
        return "\n".join(
            [
                f"game        : {h.game_id} v{h.version} disc {h.disc_number} "
                f"({h.maker_code})",
                f"name        : {h.game_name}",
                f"main.dol    : offset {h.dol_offset:#x}",
                f"FST         : offset {h.fst_offset:#x}, size {h.fst_size:#x}",
                f"files       : {len(self.files)} totalling {total:#x} bytes",
            ]
        )


def extract(data: bytes, out_dir: Path) -> DiscImage:
    """Extract an image to out_dir: sys/ (boot, bi2, apploader, dol, fst) + files/."""
    from . import dol as dol_mod

    disc = DiscImage.parse(data)
    h = disc.header
    sys_dir = out_dir / "sys"
    files_dir = out_dir / "files"
    sys_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    (sys_dir / "boot.bin").write_bytes(data[:BOOT_SIZE])
    (sys_dir / "bi2.bin").write_bytes(data[BOOT_SIZE : BOOT_SIZE + BI2_SIZE])

    ap_size, ap_trailer = struct.unpack(
        ">II", data[APPLOADER_OFFSET + 0x14 : APPLOADER_OFFSET + 0x1C]
    )
    ap_total = 0x20 + ap_size + ap_trailer
    (sys_dir / "apploader.img").write_bytes(
        data[APPLOADER_OFFSET : APPLOADER_OFFSET + ap_total]
    )

    dol_size = dol_mod.Dol.parse(data[h.dol_offset :]).file_size
    (sys_dir / "main.dol").write_bytes(data[h.dol_offset : h.dol_offset + dol_size])
    (sys_dir / "fst.bin").write_bytes(
        data[h.fst_offset : h.fst_offset + h.fst_size]
    )

    for f in disc.files:
        dest = files_dir / PurePosixPath(f.path)
        if not dest.resolve().is_relative_to(files_dir.resolve()):
            raise ValueError(f"refusing to extract outside target dir: {f.path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data[f.offset : f.offset + f.size])
    return disc


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def build(extract_dir: Path, file_alignment: int = 0x100) -> bytes:
    """Rebuild a disc image from an extract() directory tree.

    Files may have been added, removed, or resized under files/ — the FST is
    regenerated from the directory tree, and the boot header's FST fields are
    updated. This is the mod/DLC injection path.
    """
    sys_dir = extract_dir / "sys"
    files_dir = extract_dir / "files"
    boot = bytearray((sys_dir / "boot.bin").read_bytes())
    bi2 = (sys_dir / "bi2.bin").read_bytes()
    apploader = (sys_dir / "apploader.img").read_bytes()
    main_dol = (sys_dir / "main.dol").read_bytes()
    if len(boot) != BOOT_SIZE:
        raise ValueError("sys/boot.bin must be exactly 0x440 bytes")
    if len(bi2) != BI2_SIZE:
        raise ValueError("sys/bi2.bin must be exactly 0x2000 bytes")

    # --- lay out the FST from the directory tree -------------------------
    entries: list[dict] = [{"dir": True, "name": "", "parent": 0, "next": 0}]
    strings = bytearray()
    file_paths: list[Path] = []

    def add_name(name: str) -> int:
        off = len(strings)
        strings.extend(name.encode("shift-jis") + b"\x00")
        return off

    def walk(directory: Path, parent_index: int) -> None:
        children = sorted(
            directory.iterdir(),
            key=lambda p: p.name.upper(),  # FST convention: case-insensitive sort
        )
        for child in children:
            index = len(entries)
            if child.is_dir():
                entries.append(
                    {"dir": True, "name_off": add_name(child.name),
                     "parent": parent_index, "next": 0, "index": index}
                )
                walk(child, index)
                entries[index]["next"] = len(entries)
            else:
                entries.append(
                    {"dir": False, "name_off": add_name(child.name),
                     "size": child.stat().st_size, "path": child, "index": index}
                )
                file_paths.append(child)

    walk(files_dir, 0)
    num_entries = len(entries)

    # --- compute data layout ---------------------------------------------
    dol_offset = _align(APPLOADER_OFFSET + len(apploader), file_alignment)
    fst_offset = _align(dol_offset + len(main_dol), file_alignment)
    fst_size = num_entries * 12 + len(strings)
    data_start = _align(fst_offset + fst_size, file_alignment)

    offsets: dict[int, int] = {}
    cursor = data_start
    for e in entries[1:]:
        if not e["dir"]:
            offsets[e["index"]] = cursor
            cursor = _align(cursor + e["size"], file_alignment)
    total_size = cursor

    # --- serialize FST ----------------------------------------------------
    fst = bytearray()
    fst += struct.pack(">III", 1 << 24, 0, num_entries)  # root
    for e in entries[1:]:
        if e["dir"]:
            fst += struct.pack(
                ">III", (1 << 24) | e["name_off"], e["parent"], e["next"]
            )
        else:
            fst += struct.pack(
                ">III", e["name_off"], offsets[e["index"]], e["size"]
            )
    fst += strings

    # --- patch boot header -------------------------------------------------
    boot[0x420:0x430] = struct.pack(
        ">4I", dol_offset, fst_offset, fst_size, max(fst_size, 0x100000)
    )

    # --- assemble image ----------------------------------------------------
    image = bytearray(total_size)
    image[0:BOOT_SIZE] = boot
    image[BOOT_SIZE : BOOT_SIZE + BI2_SIZE] = bi2[:BI2_SIZE]
    image[APPLOADER_OFFSET : APPLOADER_OFFSET + len(apploader)] = apploader
    image[dol_offset : dol_offset + len(main_dol)] = main_dol
    image[fst_offset : fst_offset + fst_size] = fst
    for e in entries[1:]:
        if not e["dir"]:
            payload = e["path"].read_bytes()
            off = offsets[e["index"]]
            image[off : off + e["size"]] = payload
    return bytes(image)
