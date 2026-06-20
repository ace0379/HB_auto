# -*- coding: utf-8 -*-
"""Entry point: GUI when run without args, CLI when args are provided."""

from __future__ import annotations

from argparse import ArgumentParser
import sys
import time
import zipfile

from converter import iad_to_csv, validate_iad


def build_arg_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Convert IPETRONIK .iad files to CSV and Excel.")
    parser.add_argument("input_iad", help="Path to the input .iad file")
    parser.add_argument("output_dir", nargs="?", default="output/csv", help="Output directory")
    parser.add_argument("--work-dir", default="output/extracted", help="Temporary extraction directory")
    parser.add_argument("--drop-initial-seconds", type=float, default=4)
    parser.add_argument("--no-excel", action="store_true", help="Only write CSV outputs")
    return parser


def cli_main(argv: list[str]) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    start = time.time()
    try:
        validate_iad(args.input_iad)
        result_path = iad_to_csv(
            iad_path=args.input_iad,
            work_dir=args.work_dir,
            csv_dir=args.output_dir,
            drop_initial_seconds=args.drop_initial_seconds,
            write_excel=not args.no_excel,
        )
    except zipfile.BadZipFile:
        print(f"Invalid or corrupted IAD file: {args.input_iad}")
        return 1
    except Exception as exc:
        print(f"Unexpected error during conversion: {exc}")
        return 1

    elapsed = time.time() - start
    print("\n--- Conversion Summary ---")
    print(f"Input file: {args.input_iad}")
    print(f"Output merged CSV: {result_path}")
    print(f"Total execution time: {elapsed:.2f} seconds")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from gui_app import main as gui_main

        return gui_main()
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
