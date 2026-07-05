import struct

import pytest

from gcport import bti, gcm, rarc, verify, yaz0

# reuse the synthetic-disc helpers from the gcm tests
from test_gcm import make_apploader, make_boot, make_dol


def _write_extracted(root, extra_files=None):
    """Create an extract()-style tree with a couple of real archives/textures."""
    sys_dir = root / "sys"
    files_dir = root / "files" / "Course"
    sys_dir.mkdir(parents=True)
    files_dir.mkdir(parents=True)
    (sys_dir / "boot.bin").write_bytes(make_boot(name=b"verify test disc"))
    (sys_dir / "bi2.bin").write_bytes(b"\x00" * gcm.BI2_SIZE)
    (sys_dir / "apploader.img").write_bytes(make_apploader())
    (sys_dir / "main.dol").write_bytes(make_dol())

    # a plain RARC and a Yaz0-compressed RARC containing a BTI
    course = rarc.build("luigi", [
        rarc.RarcFile("course.bol", b"layout"),
        rarc.RarcFile("road.bti", bti.build(6, 4, 4, bytes(4 * 4 * 4))),
    ])
    (files_dir / "Luigi.arc").write_bytes(course)
    (files_dir / "Peach.szs").write_bytes(yaz0.compress(course))

    # a standalone BTI and standalone Yaz0
    (root / "files" / "logo.bti").write_bytes(
        bti.build(5, 8, 8, bytes(8 * 8 * 4)))
    (root / "files" / "packed.bin").write_bytes(yaz0.compress(b"hello world"))

    for rel, payload in (extra_files or {}).items():
        dest = root / "files" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
    return root


def test_verify_clean_directory(tmp_path):
    report = verify.verify(_write_extracted(tmp_path / "extract"))
    assert report.ok, report.render()
    assert "verify test disc" in report.disc_header
    assert report.formats["rarc"].ok == 2   # Luigi.arc + Peach.szs
    assert report.formats["rarc"].failed == 0
    assert report.formats["bti"].ok >= 3     # 2 inside archives + 1 standalone
    assert report.formats["yaz0"].ok == 1    # the standalone packed.bin
    assert report.dol_summary is not None
    assert report.dol_error is None


def test_verify_reports_corrupt_archive(tmp_path):
    # a file with the RARC magic but a garbage body must be reported as failed
    corrupt = rarc.MAGIC + b"\xFF" * 60
    report = verify.verify(
        _write_extracted(tmp_path / "extract",
                         {"Course/Broken.arc": corrupt}))
    assert not report.ok
    assert report.formats["rarc"].failed == 1
    assert report.formats["rarc"].errors  # captured a sample error
    path, msg = report.formats["rarc"].errors[0]
    assert "Broken.arc" in path and msg


def test_verify_reports_corrupt_bti(tmp_path):
    bad = bytearray(bti.HEADER_SIZE)
    bad[0] = 99  # invalid texture format
    struct.pack_into(">HH", bad, 2, 4, 4)
    report = verify.verify(
        _write_extracted(tmp_path / "extract", {"bad.bti": bytes(bad)}))
    assert not report.ok
    assert report.formats["bti"].failed == 1


def test_verify_iso(tmp_path):
    root = _write_extracted(tmp_path / "extract")
    iso = tmp_path / "disc.iso"
    iso.write_bytes(gcm.build(root))
    report = verify.verify(iso)
    assert report.ok, report.render()
    assert report.formats["rarc"].ok == 2
    assert report.dol_summary is not None
    # files/: Luigi.arc, Peach.szs, logo.bti, packed.bin (BTIs inside archives
    # are not separate FST entries)
    assert report.file_count == 4


def test_verify_bad_iso_magic(tmp_path):
    iso = tmp_path / "bad.iso"
    iso.write_bytes(b"\x00" * 0x1000)
    report = verify.verify(iso)
    assert not report.ok
    assert report.disc_error is not None


def test_render_is_pure_metadata(tmp_path):
    # the report must not echo file *contents*, only names/sizes/errors
    secret = b"SECRETPAYLOADBYTES"
    report = verify.verify(
        _write_extracted(tmp_path / "extract",
                         {"Course/Secret.arc": rarc.MAGIC + secret + b"\x00" * 40}))
    text = report.render()
    assert secret.decode() not in text
    assert "Secret.arc" in text  # name is fine to show
