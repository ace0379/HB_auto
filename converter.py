# -*- coding: utf-8 -*-
"""Conversion orchestration for IPETRONIK IAD files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import shutil

import numpy as np
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

    conversion_channels = channels[channels["channel_type"] != "media"].copy()

    rate_groups: dict[float, list[pd.Series]] = defaultdict(list)
    for _, row in conversion_channels.iterrows():
        rate_groups[float(row["sampleRate"])].append(row)

    for rate, rows in sorted(rate_groups.items()):
        print(f"\n=== Processing {rate:g} Hz group ===")
        df_rate = _build_rate_dataframe(work_dir, rows, drop_initial_seconds)

        if df_rate is None or df_rate.empty:
            print(f"No valid channels for {rate:g} Hz")
            continue

        output_rate = _infer_sample_rate(df_rate, rate)
        df_rate = normalize_to_ipemotion_csv(df_rate, output_rate)
        csv_path, xlsx_path = write_rate_outputs(df_rate, csv_dir, prefix, output_rate, write_excel)
        print(f"{output_rate:g} Hz CSV created: {csv_path}")
        if xlsx_path:
            print(f"{rate:g} Hz Excel created: {xlsx_path}")

    return merge_multi_rate_outputs(
        output_dir=csv_dir,
        prefix=prefix,
        rates=DEFAULT_RATES,
        write_excel=write_excel,
    )

def _infer_sample_rate(df: pd.DataFrame, fallback_rate: float) -> float:
    if df is None or df.empty or "time_s" not in df.columns or len(df) < 2:
        return fallback_rate

    diffs = pd.Series(df["time_s"]).diff().dropna()
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return fallback_rate

    step = float(diffs.median())
    if step <= 0:
        return fallback_rate

    inferred = 1.0 / step
    rounded = round(inferred)
    if abs(inferred - rounded) < 1e-6:
        return float(rounded)
    return inferred

def _remove_previous_outputs(csv_dir: Path, prefix: str) -> None:
    for pattern in (f"{prefix}_*.csv", f"{prefix}_*.xlsx"):
        for path in csv_dir.glob(pattern):
            if path.is_file():
                path.unlink()


def validate_iad(iad_path: str | Path) -> None:
    iad_path = Path(iad_path)
    if not iad_path.exists():
        raise FileNotFoundError(f"Input file not found: {iad_path}")

    try:
        with zipfile.ZipFile(iad_path, "r"):
            pass
    except zipfile.BadZipFile:
        # Some logger exports omit the ZIP central directory but still contain
        # valid local file headers, which extract_iad can recover.
        with iad_path.open("rb") as file:
            if file.read(4) != b"PK\x03\x04":
                raise


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
            df = _align_channel_to_base_time(df, base_time)

        for column in df.columns:
            if column == "time_s":
                continue
            df_rate[column] = df[column].to_numpy()

    return df_rate


def _align_channel_to_base_time(df: pd.DataFrame, base_time) -> pd.DataFrame:
    if _time_axis_matches(df["time_s"], base_time):
        aligned = df.copy()
        aligned["time_s"] = base_time
        return aligned

    base_df = pd.DataFrame({"time_s": base_time})
    if df.empty:
        return base_df

    result = base_df.copy()
    result["_base_index"] = result.index
    valid_base = result[result["time_s"].notna()].copy()
    valid_df = df[df["time_s"].notna()].copy()
    value_columns = [column for column in df.columns if column != "time_s"]
    if valid_base.empty or valid_df.empty:
        for column in value_columns:
            result[column] = np.nan
        return result.drop(columns=["_base_index"])

    base_times = pd.Series(base_time).dropna()
    diffs = base_times.diff().dropna()
    diffs = diffs[diffs > 0]
    tolerance = float(diffs.median() / 2) if not diffs.empty else 1e-9

    # Allow tiny logger/module timestamp offsets, but never carry values across
    # measurement-stop or no-value gaps that exceed half a sample period.
    aligned = pd.merge_asof(
        valid_base.sort_values("time_s"),
        valid_df.sort_values("time_s"),
        on="time_s",
        direction="nearest",
        tolerance=tolerance,
    ).set_index("_base_index")

    for column in value_columns:
        result[column] = aligned[column]

    return result.drop(columns=["_base_index"])


def _time_axis_matches(channel_time, base_time) -> bool:
    if len(channel_time) != len(base_time):
        return False

    channel_series = pd.Series(channel_time)
    base_series = pd.Series(base_time)
    channel_missing = channel_series.isna().to_numpy()
    base_missing = base_series.isna().to_numpy()
    if not np.array_equal(channel_missing, base_missing):
        return False

    valid = ~base_missing
    return np.allclose(
        channel_series.to_numpy()[valid],
        base_series.to_numpy()[valid],
        rtol=0,
        atol=1e-9,
    )
