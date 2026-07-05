import pytest

from gcport import dol


def make_sample() -> tuple[bytes, dict[str, bytes]]:
    payloads = {
        ".text0": b"\x60\x00\x00\x00" * 8,   # ppc nops
        ".text1": b"\x4E\x80\x00\x20" * 4,   # blr
        ".data0": b"hello, dolphin!\x00",
    }
    sections = [
        dol.DolSection("text", 0, 0x100, 0x8000_3100, len(payloads[".text0"])),
        dol.DolSection("text", 1, 0x120, 0x8000_3200, len(payloads[".text1"])),
        dol.DolSection("data", 0, 0x130, 0x8010_0000, len(payloads[".data0"])),
    ]
    image = dol.build(sections, bss_address=0x8020_0000, bss_size=0x1_0000,
                      entry_point=0x8000_3100, payloads=payloads)
    return image, payloads


def test_roundtrip():
    image, payloads = make_sample()
    parsed = dol.Dol.parse(image)
    assert parsed.entry_point == 0x8000_3100
    assert parsed.bss_address == 0x8020_0000
    assert parsed.bss_size == 0x1_0000
    assert [s.name for s in parsed.sections] == [".text0", ".text1", ".data0"]
    for s in parsed.sections:
        assert parsed.section_data(image, s) == payloads[s.name]


def test_file_size():
    image, _ = make_sample()
    parsed = dol.Dol.parse(image)
    assert parsed.file_size == 0x130 + len(b"hello, dolphin!\x00")
    assert parsed.file_size == len(image)


def test_truncated_rejected():
    image, _ = make_sample()
    with pytest.raises(ValueError):
        dol.Dol.parse(image[:0x80])       # smaller than header
    with pytest.raises(ValueError):
        dol.Dol.parse(image[:0x128])      # section extends past EOF


def test_describe_mentions_sections():
    image, _ = make_sample()
    text = dol.Dol.parse(image).describe()
    assert ".text0" in text and ".data0" in text and "entry point" in text
