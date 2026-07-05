"""gcport command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dol as dol_mod
from . import bti, gcm, gx_texture, png, rarc, yaz0


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


def _cmd_rarc_list(args: argparse.Namespace) -> int:
    print(rarc.Rarc.parse(Path(args.archive).read_bytes()).describe())
    return 0


def _cmd_rarc_extract(args: argparse.Namespace) -> int:
    arc = rarc.extract(Path(args.archive).read_bytes(), Path(args.output))
    print(f"extracted {len(arc.files)} files to {args.output}")
    return 0


def _cmd_rarc_create(args: argparse.Namespace) -> int:
    from . import yaz0 as yaz0_mod

    image = rarc.create_from_dir(Path(args.directory), args.root_name)
    if args.yaz0:
        image = yaz0_mod.compress(image)
    Path(args.output).write_bytes(image)
    print(f"created {args.output} ({len(image):#x} bytes)")
    return 0


def _cmd_bti_info(args: argparse.Namespace) -> int:
    print(bti.Bti.parse(Path(args.texture).read_bytes()).describe())
    return 0


def _cmd_bti_decode(args: argparse.Namespace) -> int:
    tex = bti.Bti.parse(Path(args.texture).read_bytes())
    Path(args.output).write_bytes(png.write(tex.width, tex.height, tex.rgba))
    print(f"decoded {tex.width}x{tex.height} "
          f"{gx_texture.FORMAT_NAMES[tex.format]} -> {args.output}")
    return 0


def _cmd_bti_encode(args: argparse.Namespace) -> int:
    fmt = gx_texture.NAME_TO_FORMAT.get(args.format.upper())
    if fmt is None or fmt not in gx_texture.ENCODABLE:
        supported = ", ".join(
            gx_texture.FORMAT_NAMES[f] for f in sorted(gx_texture.ENCODABLE))
        print(f"error: format must be one of: {supported}", file=sys.stderr)
        return 1
    width, height, rgba = png.read(Path(args.input).read_bytes())
    Path(args.output).write_bytes(bti.build(fmt, width, height, rgba))
    print(f"encoded {width}x{height} as {args.format.upper()} -> {args.output}")
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

    p_rarc = sub.add_parser("rarc", help="RARC archives (.arc/.szs)")
    rarc_sub = p_rarc.add_subparsers(dest="subcommand", required=True)
    p = rarc_sub.add_parser("list", help="list archive contents")
    p.add_argument("archive")
    p.set_defaults(func=_cmd_rarc_list)
    p = rarc_sub.add_parser("extract", help="extract archive to a directory")
    p.add_argument("archive")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=_cmd_rarc_extract)
    p = rarc_sub.add_parser("create", help="create an archive from a directory")
    p.add_argument("directory")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--root-name", default=None,
                   help="archive root node name (default: directory name)")
    p.add_argument("--yaz0", action="store_true",
                   help="Yaz0-compress the result (.szs style)")
    p.set_defaults(func=_cmd_rarc_create)

    p_bti = sub.add_parser("bti", help="BTI textures")
    bti_sub = p_bti.add_subparsers(dest="subcommand", required=True)
    p = bti_sub.add_parser("info", help="show texture format and size")
    p.add_argument("texture")
    p.set_defaults(func=_cmd_bti_info)
    p = bti_sub.add_parser("decode", help="decode a BTI to PNG")
    p.add_argument("texture")
    p.add_argument("output")
    p.set_defaults(func=_cmd_bti_decode)
    p = bti_sub.add_parser("encode", help="encode a PNG to BTI")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--format", default="RGB5A3",
                   help="GX texture format (default RGB5A3)")
    p.set_defaults(func=_cmd_bti_encode)

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
