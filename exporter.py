# -*- coding: utf-8 -*-
"""CSV and Excel export helpers for converted IAD data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_RATES = (1, 10, 100, 1000)


def write_rate_outputs(
    df: pd.DataFrame,
    output_dir: str | Path,
    prefix: str,
    rate: float,
    write_excel: bool = True,
) -> tuple[Path, Path | None]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rate_label = _rate_label(rate)
    csv_path = output_dir / f"{prefix}_{rate_label}Hz.csv"
    xlsx_path = output_dir / f"{prefix}_{rate_label}Hz.xlsx"

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    if write_excel:
        df.to_excel(xlsx_path, index=False)
        return csv_path, xlsx_path
    return csv_path, None


def merge_multi_rate_outputs(
    output_dir: str | Path,
    prefix: str,
    rates=DEFAULT_RATES,
    output_csv: str | Path | None = None,
    output_xlsx: str | Path | None = None,
    write_excel: bool = True,
) -> Path:
    """Merge per-rate CSVs column-wise, preserving legacy all_rates behavior."""
    output_dir = Path(output_dir)
    output_csv = Path(output_csv) if output_csv else output_dir / f"{prefix}_all_rates.csv"
    output_xlsx = Path(output_xlsx) if output_xlsx else output_dir / f"{prefix}_all_rates.xlsx"

    dfs = []
    max_len = 0

    for rate in rates:
        csv_path = output_dir / f"{prefix}_{_rate_label(rate)}Hz.csv"
        if not csv_path.exists():
            print(f"{rate} Hz CSV not found, skip")
            continue

        df = pd.read_csv(csv_path, low_memory=False)
        dfs.append(df)
        max_len = max(max_len, len(df))
        print(f"{rate} Hz loaded ({len(df)} rows)")

    if not dfs:
        raise RuntimeError("No CSV files to merge")

    merged_df = pd.concat([df.reindex(range(max_len)) for df in dfs], axis=1)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    if write_excel:
        merged_df.to_excel(output_xlsx, index=False)

    print(f"Merged all-rates CSV created: {output_csv}")
    return output_csv


def _rate_label(rate: float | int) -> str:
    rate = float(rate)
    return str(int(rate)) if rate.is_integer() else str(rate).replace(".", "p")
