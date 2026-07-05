"""RARC archive format (Nintendo first-party .arc files, e.g. MKDD courses).

Implemented from community documentation (Cloud Modding wiki, WArchive-Tools).
Round-trip tested against itself; **not yet verified against retail archives**
— that check happens as soon as a user-supplied dump is available.

Layout (all big-endian):
  0x00  header (0x20): "RARC" magic, file size, header size (0x20),
        data offset (rel 0x20), data size, MRAM size, ARAM size, pad
  0x20  info block (0x20, internal offsets relative to 0x20):
        node count/offset, file entry count/offset, string table
        size/offset, next free file id (u16), sync-ids flag (u8), pad
  Node (0x10): 4-char identifier, name offset, name hash (u16),
        entry count (u16), first entry index (u32)
  File entry (0x14): id (u16, 0xFFFF for dirs), name hash (u16), flags (u8),
        pad, name offset (u16), data offset (files, rel to data start) or
        node index (dirs), data size, pad
  Every directory's entry list ends with "." and ".." directory entries.

Flags: 0x01 file, 0x02 directory, 0x04 compressed, 0x10 MRAM preload,
       0x80 Yaz0 (with 0x04).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import yaz0

MAGIC = b"RARC"
HEADER_SIZE = 0x20
FLAG_FILE = 0x01
FLAG_DIR = 0x02
FLAG_COMPRESSED = 0x04
FLAG_MRAM = 0x10
FLAG_YAZ0 = 0x80
DEFAULT_FILE_FLAGS = FLAG_FILE | FLAG_MRAM


def name_hash(name: str) -> int:
    h = 0
    for b in name.encode("shift-jis"):
        h = (h * 3 + b) & 0xFFFF
    return h


@dataclass
class RarcFile:
    path: str  # posix path relative to archive root (root dir name excluded)
    data: bytes


@dataclass
class Rarc:
    root_name: str
    files: list[RarcFile] = field(default_factory=list)

    @classmethod
    def parse(cls, data: bytes) -> "Rarc":
        if yaz0.is_yaz0(data):
            data = yaz0.decompress(data)
        if data[:4] != MAGIC:
            raise ValueError("not a RARC archive (bad magic)")
        data_offset_rel = struct.unpack(">I", data[0x0C:0x10])[0]
        data_start = HEADER_SIZE + data_offset_rel

        (num_nodes, node_off, num_entries, entry_off,
         _strings_size, strings_off) = struct.unpack(">6I", data[0x20:0x38])
        node_base = HEADER_SIZE + node_off
        entry_base = HEADER_SIZE + entry_off
        strings_base = HEADER_SIZE + strings_off

        def string_at(off: int) -> str:
            end = data.index(b"\x00", strings_base + off)
            return data[strings_base + off : end].decode("shift-jis", "replace")

        nodes = []
        for i in range(num_nodes):
            base = node_base + i * 0x10
            _ident = data[base : base + 4]
            name_off, _hash, n_entries, first = struct.unpack(
                ">IHHI", data[base + 4 : base + 0x10]
            )
            nodes.append((string_at(name_off), n_entries, first))

        def entry_at(index: int):
            base = entry_base + index * 0x14
            fid, _hash, flags, _pad, name_off, off_or_node, size, _pad2 = (
                struct.unpack(">HHBBHIII", data[base : base + 0x14])
            )
            return fid, flags, string_at(name_off), off_or_node, size

        if not nodes:
            raise ValueError("RARC has no root node")

        files: list[RarcFile] = []

        def walk(node_index: int, prefix: str) -> None:
            _name, n_entries, first = nodes[node_index]
            for i in range(first, first + n_entries):
                _fid, flags, name, off_or_node, size = entry_at(i)
                if name in (".", ".."):
                    continue
                if flags & FLAG_DIR:
                    walk(off_or_node, f"{prefix}{name}/")
                else:
                    payload = data[data_start + off_or_node :
                                   data_start + off_or_node + size]
                    if flags & FLAG_YAZ0 and yaz0.is_yaz0(payload):
                        payload = yaz0.decompress(payload)
                    files.append(RarcFile(path=f"{prefix}{name}", data=payload))

        walk(0, "")
        return cls(root_name=nodes[0][0], files=files)

    def describe(self) -> str:
        total = sum(len(f.data) for f in self.files)
        lines = [f"root        : {self.root_name}",
                 f"files       : {len(self.files)} totalling {total:#x} bytes"]
        for f in self.files:
            lines.append(f"  {len(f.data):>10}  {f.path}")
        return "\n".join(lines)


def _align(value: int, alignment: int = 0x20) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def build(root_name: str, files: list[RarcFile]) -> bytes:
    """Build a RARC archive. Directory structure is inferred from file paths."""
    # --- build the directory tree ----------------------------------------
    # tree: dir path ("" = root) -> (subdir names, files) in insertion order
    tree: dict[str, tuple[list[str], list[RarcFile]]] = {"": ([], [])}

    def ensure_dir(path: str) -> None:
        if path in tree:
            return
        parent, _, name = path.rpartition("/")
        ensure_dir(parent)
        tree[parent][0].append(name)
        tree[path] = ([], [])

    for f in files:
        parent, _, _name = f.path.rpartition("/")
        ensure_dir(parent)
        tree[parent][1].append(f)

    # --- string table ------------------------------------------------------
    strings = bytearray(b".\x00..\x00")
    string_offsets: dict[str, int] = {".": 0, "..": 2}

    def intern(name: str) -> int:
        if name not in string_offsets:
            string_offsets[name] = len(strings)
            strings.extend(name.encode("shift-jis") + b"\x00")
        return string_offsets[name]

    intern(root_name)

    # --- assign node indices (preorder) ------------------------------------
    dir_paths: list[str] = []

    def collect(path: str) -> None:
        dir_paths.append(path)
        for sub in tree[path][0]:
            collect(f"{path}/{sub}" if path else sub)

    collect("")
    node_index = {path: i for i, path in enumerate(dir_paths)}

    # --- lay out entries and file data --------------------------------------
    nodes: list[tuple[str, int, int]] = []  # (name, num_entries, first_index)
    entries: list[tuple[int, int, str, int, int]] = []  # id,flags,name,off/node,size
    data_blob = bytearray()
    next_id = 0

    for path in dir_paths:
        subdirs, dir_files = tree[path]
        name = root_name if path == "" else path.rpartition("/")[2]
        parent = None if path == "" else path.rpartition("/")[0]
        first = len(entries)
        for f in dir_files:
            offset = len(data_blob)
            data_blob.extend(f.data)
            data_blob.extend(b"\x00" * (_align(len(data_blob)) - len(data_blob)))
            fname = f.path.rpartition("/")[2]
            intern(fname)
            entries.append((next_id, DEFAULT_FILE_FLAGS, fname, offset, len(f.data)))
            next_id += 1
        for sub in subdirs:
            sub_path = f"{path}/{sub}" if path else sub
            intern(sub)
            entries.append((0xFFFF, FLAG_DIR, sub, node_index[sub_path], 0x10))
        entries.append((0xFFFF, FLAG_DIR, ".", node_index[path], 0x10))
        entries.append(
            (0xFFFF, FLAG_DIR, "..",
             0xFFFFFFFF if parent is None else node_index[parent], 0x10)
        )
        nodes.append((name, len(entries) - first, first))

    # --- serialize -----------------------------------------------------------
    node_table = bytearray()
    for i, (name, n_entries, first) in enumerate(nodes):
        ident = b"ROOT" if i == 0 else name.upper().encode(
            "shift-jis", "replace")[:4].ljust(4, b" ")
        node_table += ident
        node_table += struct.pack(">IHHI", string_offsets[name],
                                  name_hash(name), n_entries, first)

    entry_table = bytearray()
    for fid, flags, name, off_or_node, size in entries:
        entry_table += struct.pack(
            ">HHBBHIII", fid, name_hash(name), flags, 0,
            string_offsets[name], off_or_node & 0xFFFFFFFF, size, 0
        )

    node_off = 0x20  # relative to info block base (abs 0x40)
    entry_off = _align(node_off + len(node_table))
    strings_off = _align(entry_off + len(entry_table))
    data_off = _align(strings_off + len(strings))

    info = struct.pack(
        ">6IHB5x",
        len(nodes), node_off, len(entries), entry_off,
        _align(len(strings)), strings_off, next_id, 1
    )

    total_size = HEADER_SIZE + data_off + len(data_blob)
    header = MAGIC + struct.pack(
        ">7I", total_size, HEADER_SIZE, data_off, len(data_blob),
        len(data_blob), 0, 0
    )

    out = bytearray(HEADER_SIZE + data_off)
    out[0:HEADER_SIZE] = header
    out[HEADER_SIZE : HEADER_SIZE + len(info)] = info
    base = HEADER_SIZE
    out[base + node_off : base + node_off + len(node_table)] = node_table
    out[base + entry_off : base + entry_off + len(entry_table)] = entry_table
    out[base + strings_off : base + strings_off + len(strings)] = strings
    out += data_blob
    return bytes(out)


def extract(data: bytes, out_dir: Path) -> Rarc:
    arc = Rarc.parse(data)
    for f in arc.files:
        dest = out_dir / f.path
        if not dest.resolve().is_relative_to(out_dir.resolve()):
            raise ValueError(f"refusing to extract outside target dir: {f.path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(f.data)
    return arc


def create_from_dir(root_dir: Path, root_name: str | None = None) -> bytes:
    files: list[RarcFile] = []
    for path in sorted(root_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root_dir).as_posix()
            files.append(RarcFile(path=rel, data=path.read_bytes()))
    return build(root_name or root_dir.name, files)
