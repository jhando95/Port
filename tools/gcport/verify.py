"""One-shot dump verifier: parse everything gcport understands and report.

Given either an extracted disc directory (from `gcport iso extract`) or a raw
ISO, this walks the file tree, classifies each file by magic/extension, and
attempts to parse it with the matching gcport parser. It reports how many of
each format parsed, a handful of sample failures with their errors, and a
final verdict — the fast way to confirm the parsers handle a real retail dump
(and to surface exactly what to fix if they don't).

No file contents are printed, only names, sizes, formats, and error text.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import bti, dol, gcm, rarc, yaz0

MAX_SAMPLE_ERRORS = 5
# Skip decoding files larger than this when only a parse check is wanted;
# archives can be large but we still parse them — this guards pathological
# reads only. 0 = no limit.
LARGE_FILE_WARN = 64 * 1024 * 1024


@dataclass
class FormatResult:
    name: str
    ok: int = 0
    failed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)  # (path, msg)

    def record(self, path: str, error: str | None) -> None:
        if error is None:
            self.ok += 1
        else:
            self.failed += 1
            if len(self.errors) < MAX_SAMPLE_ERRORS:
                self.errors.append((path, error))

    @property
    def total(self) -> int:
        return self.ok + self.failed


@dataclass
class VerifyReport:
    source: str
    disc_header: str | None = None
    disc_error: str | None = None
    file_count: int = 0
    total_bytes: int = 0
    formats: dict[str, FormatResult] = field(default_factory=dict)
    dol_summary: str | None = None
    dol_error: str | None = None
    notes: list[str] = field(default_factory=list)

    def fmt(self, name: str) -> FormatResult:
        return self.formats.setdefault(name, FormatResult(name))

    @property
    def ok(self) -> bool:
        if self.disc_error:
            return False
        if self.dol_error:
            return False
        return all(f.failed == 0 for f in self.formats.values())

    def render(self) -> str:
        lines: list[str] = []
        lines.append(f"gcport verify — {self.source}")
        lines.append("=" * 60)
        if self.disc_header:
            lines.append(self.disc_header)
        if self.disc_error:
            lines.append(f"DISC HEADER ERROR: {self.disc_error}")
        lines.append(f"files scanned : {self.file_count} "
                     f"({self.total_bytes / 1_000_000:.1f} MB)")
        lines.append("")

        if not self.formats:
            lines.append("no recognized formats found")
        else:
            lines.append(f"{'format':<10} {'parsed':>8} {'failed':>8}")
            lines.append(f"{'-'*10} {'-'*8:>8} {'-'*8:>8}")
            for name in sorted(self.formats):
                f = self.formats[name]
                flag = "" if f.failed == 0 else "  <-- needs attention"
                lines.append(f"{name:<10} {f.ok:>8} {f.failed:>8}{flag}")

        if self.dol_summary:
            lines.append("")
            lines.append("main.dol:")
            for line in self.dol_summary.splitlines():
                lines.append(f"  {line}")
        if self.dol_error:
            lines.append(f"main.dol ERROR: {self.dol_error}")

        # sample failures
        failing = [f for f in self.formats.values() if f.errors]
        if failing:
            lines.append("")
            lines.append("sample failures (first few per format):")
            for f in failing:
                lines.append(f"  [{f.name}]")
                for path, msg in f.errors:
                    lines.append(f"    {path}: {msg}")

        if self.notes:
            lines.append("")
            for note in self.notes:
                lines.append(f"note: {note}")

        lines.append("")
        lines.append("VERDICT: " + ("all parsers OK" if self.ok
                                     else "some parsers failed — see above"))
        return "\n".join(lines)


def _looks_like_rarc(data: bytes) -> bool:
    if data[:4] == rarc.MAGIC:
        return True
    if yaz0.is_yaz0(data):
        # peek past the Yaz0 header cheaply by decompressing just enough
        try:
            return yaz0.decompress(data)[:4] == rarc.MAGIC
        except Exception:
            return False
    return False


def _classify_and_check(path: str, data: bytes, report: VerifyReport) -> None:
    lower = path.lower()

    # RARC / szs archives (by magic, robust to extension)
    if _looks_like_rarc(data):
        try:
            arc = rarc.Rarc.parse(data)
            report.fmt("rarc").record(path, None)
            # opportunistically verify BTIs inside the archive
            for entry in arc.files:
                if entry.path.lower().endswith(".bti"):
                    _check_bti(f"{path}!{entry.path}", entry.data, report)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            report.fmt("rarc").record(path, f"{type(exc).__name__}: {exc}")
        return

    # standalone Yaz0 (not wrapping a RARC)
    if yaz0.is_yaz0(data):
        try:
            yaz0.decompress(data)
            report.fmt("yaz0").record(path, None)
        except Exception as exc:  # noqa: BLE001
            report.fmt("yaz0").record(path, f"{type(exc).__name__}: {exc}")
        return

    # standalone BTI textures (by extension; BTI has no magic)
    if lower.endswith(".bti"):
        _check_bti(path, data, report)
        return


def _check_bti(path: str, data: bytes, report: VerifyReport) -> None:
    try:
        bti.Bti.parse(data)
        report.fmt("bti").record(path, None)
    except Exception as exc:  # noqa: BLE001
        report.fmt("bti").record(path, f"{type(exc).__name__}: {exc}")


def verify_directory(root: Path) -> VerifyReport:
    report = VerifyReport(source=str(root))
    files_dir = root / "files"
    sys_dir = root / "sys"
    scan_root = files_dir if files_dir.is_dir() else root

    boot = sys_dir / "boot.bin"
    if boot.is_file():
        try:
            header = gcm.DiscHeader.parse(boot.read_bytes())
            report.disc_header = (
                f"game {header.game_id} v{header.version} — "
                f"{header.game_name}")
        except Exception as exc:  # noqa: BLE001
            report.disc_error = f"{type(exc).__name__}: {exc}"

    for path in sorted(scan_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(scan_root).as_posix()
        size = path.stat().st_size
        report.file_count += 1
        report.total_bytes += size
        if LARGE_FILE_WARN and size > LARGE_FILE_WARN:
            report.notes.append(f"{rel} is large ({size/1e6:.0f} MB)")
        try:
            data = path.read_bytes()
        except OSError as exc:
            report.notes.append(f"could not read {rel}: {exc}")
            continue
        _classify_and_check(rel, data, report)

    dol_path = sys_dir / "main.dol"
    if dol_path.is_file():
        _check_dol(dol_path.read_bytes(), report)

    return report


def verify_iso(iso_path: Path) -> VerifyReport:
    data = iso_path.read_bytes()
    report = VerifyReport(source=str(iso_path))
    try:
        disc = gcm.DiscImage.parse(data)
        report.disc_header = (
            f"game {disc.header.game_id} v{disc.header.version} — "
            f"{disc.header.game_name}")
    except Exception as exc:  # noqa: BLE001
        report.disc_error = f"{type(exc).__name__}: {exc}"
        return report

    for f in disc.files:
        report.file_count += 1
        report.total_bytes += f.size
        _classify_and_check(f.path, data[f.offset:f.offset + f.size], report)

    # main.dol straight from the image
    try:
        _check_dol(data[disc.header.dol_offset:], report)
    except Exception as exc:  # noqa: BLE001
        report.dol_error = f"{type(exc).__name__}: {exc}"
    return report


def _check_dol(data: bytes, report: VerifyReport) -> None:
    try:
        parsed = dol.Dol.parse(data)
        report.dol_summary = parsed.describe()
    except Exception as exc:  # noqa: BLE001
        report.dol_error = f"{type(exc).__name__}: {exc}"


def verify(source: Path) -> VerifyReport:
    """Verify an extracted directory or a raw ISO; dispatches on what's there."""
    if source.is_dir():
        return verify_directory(source)
    return verify_iso(source)
