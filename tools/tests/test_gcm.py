import struct
from pathlib import Path

import pytest

from gcport import dol, gcm


def make_boot(game_id=b"GM4E", maker=b"01", name=b"synthetic test disc") -> bytes:
    boot = bytearray(gcm.BOOT_SIZE)
    boot[0:4] = game_id
    boot[4:6] = maker
    boot[6] = 0      # disc number
    boot[7] = 0      # version
    boot[0x1C:0x20] = struct.pack(">I", gcm.DVD_MAGIC)
    boot[0x20 : 0x20 + len(name)] = name
    # DOL/FST offsets are filled in by gcm.build()
    return bytes(boot)


def make_apploader() -> bytes:
    code = b"\x60\x00\x00\x00" * 16
    header = bytearray(0x20)
    header[0:10] = b"2026/07/05"
    header[0x10:0x14] = struct.pack(">I", 0x8120_0000)   # entry
    header[0x14:0x18] = struct.pack(">I", len(code))     # size
    header[0x18:0x1C] = struct.pack(">I", 0)             # trailer size
    return bytes(header) + code


def make_dol() -> bytes:
    payload = b"\x4E\x80\x00\x20" * 8
    return dol.build(
        [dol.DolSection("text", 0, 0x100, 0x8000_3100, len(payload))],
        bss_address=0, bss_size=0, entry_point=0x8000_3100,
        payloads={".text0": payload},
    )


FILES = {
    "opening.bnr": b"banner data here",
    "Course/Luigi.arc": b"luigi circuit course archive",
    "Course/Peach.arc": b"peach beach course archive" * 10,
    "AudioRes/Stream/song.ast": b"\x00\x01" * 300,
}


def make_tree(root: Path, files=FILES) -> Path:
    sys_dir = root / "sys"
    sys_dir.mkdir(parents=True)
    (sys_dir / "boot.bin").write_bytes(make_boot())
    (sys_dir / "bi2.bin").write_bytes(b"\x00" * gcm.BI2_SIZE)
    (sys_dir / "apploader.img").write_bytes(make_apploader())
    (sys_dir / "main.dol").write_bytes(make_dol())
    for rel, payload in files.items():
        dest = root / "files" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    return root


def test_build_and_parse(tmp_path):
    image = gcm.build(make_tree(tmp_path / "tree"))
    disc = gcm.DiscImage.parse(image)
    assert disc.header.game_id == "GM4E"
    assert disc.header.game_name == "synthetic test disc"
    assert {f.path for f in disc.files} == set(FILES)
    for f in disc.files:
        assert image[f.offset : f.offset + f.size] == FILES[f.path]


def test_extract_roundtrip(tmp_path):
    image = gcm.build(make_tree(tmp_path / "tree"))
    out = tmp_path / "extracted"
    gcm.extract(image, out)
    for rel, payload in FILES.items():
        assert (out / "files" / rel).read_bytes() == payload
    assert (out / "sys" / "main.dol").read_bytes() == make_dol()
    assert (out / "sys" / "boot.bin").read_bytes()[:4] == b"GM4E"
    # rebuild from the extraction and confirm the image is stable
    image2 = gcm.build(out)
    assert image2 == image


def test_dlc_injection_roundtrip(tmp_path):
    """The core mod loop: extract, add a file, rebuild, re-extract."""
    image = gcm.build(make_tree(tmp_path / "tree"))
    out = tmp_path / "extracted"
    gcm.extract(image, out)

    new_track = b"custom rainbow road!!" * 20
    (out / "files" / "Course" / "Custom.arc").write_bytes(new_track)
    (out / "files" / "Course" / "Luigi.arc").write_bytes(b"resized" * 99)

    modded = gcm.build(out)
    disc = gcm.DiscImage.parse(modded)
    paths = {f.path for f in disc.files}
    assert "Course/Custom.arc" in paths
    by_path = {f.path: f for f in disc.files}
    f = by_path["Course/Custom.arc"]
    assert modded[f.offset : f.offset + f.size] == new_track
    f = by_path["Course/Luigi.arc"]
    assert modded[f.offset : f.offset + f.size] == b"resized" * 99


def test_file_alignment(tmp_path):
    image = gcm.build(make_tree(tmp_path / "tree"), file_alignment=0x800)
    disc = gcm.DiscImage.parse(image)
    for f in disc.files:
        assert f.offset % 0x800 == 0


def test_bad_magic_rejected():
    with pytest.raises(ValueError):
        gcm.DiscImage.parse(b"\x00" * 0x1000)


def test_nested_dirs_and_sorting(tmp_path):
    files = {
        "b/deep/nested/one.bin": b"1",
        "b/deep/two.bin": b"2",
        "a.bin": b"a",
        "Z.bin": b"z",
    }
    image = gcm.build(make_tree(tmp_path / "tree", files))
    disc = gcm.DiscImage.parse(image)
    assert {f.path for f in disc.files} == set(files)
