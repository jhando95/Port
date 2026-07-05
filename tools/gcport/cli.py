"""gcport command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dol as dol_mod
from . import gcm, yaz0


def _cmd_iso_info(args: argparse.Namespace) -> int:
    disc = gcm.DiscImage.parse(Path(args.image).read_bytes())
    print(disc.describe())
    if args.list:
        for f in disc.files:
            print(f"{f.size:>10}  {f.path}")
    return 0


def _cmd_iso_extract(args: argparse.Namespace) -> int:
    disc = gcm.extract(Path(args.image).read_bytes(), Path(args.output))
    print(f"extracted {len(disc.files)} files to {args.output}")
    return 0


def _cmd_iso_build(args: argparse.Namespace) -> int:
    image = gcm.build(Path(args.directory), file_alignment=args.align)
    Path(args.output).write_bytes(image)
    print(f"built {args.output} ({len(image):#x} bytes)")
    return 0


def _cmd_dol_info(args: argparse.Namespace) -> int:
    print(dol_mod.Dol.parse(Path(args.dol).read_bytes()).describe())
    return 0


def _cmd_yaz0_decompress(args: argparse.Namespace) -> int:
    Path(args.output).write_bytes(yaz0.decompress(Path(args.input).read_bytes()))
    return 0


def _cmd_yaz0_compress(args: argparse.Namespace) -> int:
    Path(args.output).write_bytes(yaz0.compress(Path(args.input).read_bytes()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gcport", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_iso = sub.add_parser("iso", help="GCM/ISO disc images")
    iso_sub = p_iso.add_subparsers(dest="subcommand", required=True)

    p = iso_sub.add_parser("info", help="show disc header and stats")
    p.add_argument("image")
    p.add_argument("--list", action="store_true", help="list all files")
    p.set_defaults(func=_cmd_iso_info)

    p = iso_sub.add_parser("extract", help="extract sys/ and files/ from an image")
    p.add_argument("image")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=_cmd_iso_extract)

    p = iso_sub.add_parser("build", help="rebuild an image from an extracted tree")
    p.add_argument("directory")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--align", type=lambda s: int(s, 0), default=0x100,
                   help="file data alignment (default 0x100)")
    p.set_defaults(func=_cmd_iso_build)

    p_dol = sub.add_parser("dol", help="DOL executables")
    dol_sub = p_dol.add_subparsers(dest="subcommand", required=True)
    p = dol_sub.add_parser("info", help="show DOL header, sections, entry point")
    p.add_argument("dol")
    p.set_defaults(func=_cmd_dol_info)

    p_yaz0 = sub.add_parser("yaz0", help="Yaz0 compression")
    yaz0_sub = p_yaz0.add_subparsers(dest="subcommand", required=True)
    p = yaz0_sub.add_parser("decompress")
    p.add_argument("input")
    p.add_argument("output")
    p.set_defaults(func=_cmd_yaz0_decompress)
    p = yaz0_sub.add_parser("compress")
    p.add_argument("input")
    p.add_argument("output")
    p.set_defaults(func=_cmd_yaz0_compress)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
