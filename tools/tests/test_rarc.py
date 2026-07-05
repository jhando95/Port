import pytest

from gcport import rarc, yaz0

FILES = [
    rarc.RarcFile("course.bol", b"course layout data"),
    rarc.RarcFile("course_model.bmd", b"model geometry" * 40),
    rarc.RarcFile("objects/tree.bmd", b"a tree"),
    rarc.RarcFile("objects/textures/bark.bti", b"\x01\x02" * 64),
    rarc.RarcFile("empty.bin", b""),
]


def test_roundtrip():
    image = rarc.build("luigi", FILES)
    arc = rarc.Rarc.parse(image)
    assert arc.root_name == "luigi"
    assert {f.path for f in arc.files} == {f.path for f in FILES}
    by_path = {f.path: f.data for f in arc.files}
    for f in FILES:
        assert by_path[f.path] == f.data


def test_yaz0_wrapped_archive():
    image = rarc.build("luigi", FILES)
    compressed = yaz0.compress(image)
    arc = rarc.Rarc.parse(compressed)  # transparent decompression
    assert {f.path for f in arc.files} == {f.path for f in FILES}


def test_file_data_aligned():
    image = rarc.build("x", FILES)
    data_offset_rel = int.from_bytes(image[0x0C:0x10], "big")
    assert (rarc.HEADER_SIZE + data_offset_rel) % 0x20 == 0


def test_extract_and_create_from_dir(tmp_path):
    image = rarc.build("luigi", FILES)
    out = tmp_path / "unpacked"
    rarc.extract(image, out)
    assert (out / "objects" / "tree.bmd").read_bytes() == b"a tree"
    rebuilt = rarc.create_from_dir(out, "luigi")
    arc = rarc.Rarc.parse(rebuilt)
    assert {f.path for f in arc.files} == {f.path for f in FILES}
    by_path = {f.path: f.data for f in arc.files}
    for f in FILES:
        assert by_path[f.path] == f.data


def test_mod_injection(tmp_path):
    """The DLC loop at archive level: extract, add file, rebuild."""
    out = tmp_path / "unpacked"
    rarc.extract(rarc.build("luigi", FILES), out)
    (out / "objects" / "custom_item.bmd").write_bytes(b"new dlc object")
    arc = rarc.Rarc.parse(rarc.create_from_dir(out, "luigi"))
    by_path = {f.path: f.data for f in arc.files}
    assert by_path["objects/custom_item.bmd"] == b"new dlc object"
    assert by_path["course.bol"] == b"course layout data"


def test_name_hash():
    # hash is h = h*3 + byte over shift-jis bytes, mod 2^16
    assert rarc.name_hash("") == 0
    assert rarc.name_hash("a") == ord("a")
    assert rarc.name_hash("ab") == (ord("a") * 3 + ord("b")) & 0xFFFF


def test_bad_magic_rejected():
    with pytest.raises(ValueError):
        rarc.Rarc.parse(b"NARC" + b"\x00" * 64)
