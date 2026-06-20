# -*- coding: utf-8 -*-
"""Conversion orchestration for IPETRONIK IAD files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import shutil
import zipfile

import pandas as pd

from channel_cleaner import ensure_unique_channel_names, normalize_to_ipemotion_csv
from exporter import DEFAULT_RATES, merge_multi_rate_outputs, write_rate_outputs
from iad_parser import (
    cha_to_dataframe,
    extract_iad,
    extract_xml_from_ird,
    find_cha_file,
    find_ird_file,
    parse_channels,
)


def iad_to_csv(
    iad_path: str | Path,
    work_dir: str | Path = "output/extracted",
    csv_dir: str | Path = "output/csv",
    prefix: str | None = None,
    drop_initial_seconds: float = 4,
    write_excel: bool = True,
) -> Path:
    """Convert an .iad file to rate CSVs plus a merged all-rates CSV."""
    iad_path = Path(iad_path)
    work_dir = Path(work_dir)
    csv_dir = Path(csv_dir)
    prefix = prefix or iad_path.stem

    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)
    _remove_previous_outputs(csv_dir, prefix)

    extract_iad(iad_path, work_dir)

    ird_file = find_ird_file(work_dir)
    xml_path = extract_xml_from_ird(ird_file, work_dir / "metadata.xml")
    channels = ensure_unique_channel_names(parse_channels(xml_path))

    channels.to_csv(csv_dir / f"{prefix}_channels.csv", index=False, encoding="utf-8-sig")
    if write_excel:
        channels.to_excel(csv_dir / f"{prefix}_channels.xlsx", index=False)

    rate_groups: dict[float, list[pd.Series]] = defaultdict(list)
    for _, row in channels.iterrows():
        rate_groups[float(row["sampleRate"])].append(row)

    for rate, rows in sorted(rate_groups.items()):
        print(f"\n=== Processing {rate:g} Hz group ===")
        df_rate = _build_rate_dataframe(work_dir, rows, drop_initial_seconds)

        if df_rate is None or df_rate.empty:
            print(f"No valid channels for {rate:g} Hz")
            continue

        df_rate = normalize_to_ipemotion_csv(df_rate, rate)
        csv_path, xlsx_path = write_rate_outputs(df_rate, csv_dir, prefix, rate, write_excel)
        print(f"{rate:g} Hz CSV created: {csv_path}")
        if xlsx_path:
            print(f"{rate:g} Hz Excel created: {xlsx_path}")

    return merge_multi_rate_outputs(
        output_dir=csv_dir,
        prefix=prefix,
        rates=DEFAULT_RATES,
        write_excel=write_excel,
    )


def _remove_previous_outputs(csv_dir: Path, prefix: str) -> None:
    for pattern in (f"{prefix}_*.csv", f"{prefix}_*.xlsx"):
        for path in csv_dir.glob(pattern):
            if path.is_file():
                path.unlink()


def validate_iad(iad_path: str | Path) -> None:
    iad_path = Path(iad_path)
    if not iad_path.exists():
        raise FileNotFoundError(f"Input file not found: {iad_path}")
    with zipfile.ZipFile(iad_path, "r"):
        pass


def _build_rate_dataframe(
    work_dir: Path,
    rows: list[pd.Series],
    drop_initial_seconds: float,
) -> pd.DataFrame | None:
    base_time = None
    df_rate = None

    for row in rows:
        cha_path = find_cha_file(work_dir, row["id"])
        if cha_path is None:
            print(f"CHA not found for channel id {row['id']} ({row['name']}), skip")
            continue

        try:
            df = cha_to_dataframe(
                cha_path=cha_path,
                ch_meta=row,
                drop_initial_seconds=drop_initial_seconds,
            )
        except ValueError as exc:
            print(f"{exc} for channel id {row['id']} ({row['name']}), skip")
            continue

        if df.empty:
            continue

        if base_time is None:
            base_time = df["time_s"].values
            df_rate = df[["time_s"]].copy()
        else:
            min_len = min(len(df), len(base_time), len(df_rate))
            df = df.iloc[:min_len].copy()
            df_rate = df_rate.iloc[:min_len].copy()
            base_time = base_time[:min_len]
            df["time_s"] = base_time

        df_rate = df_rate.merge(df, on="time_s", how="left")

    return df_rate
