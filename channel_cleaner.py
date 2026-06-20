# -*- coding: utf-8 -*-
"""Channel name cleanup and IPEmotion-compatible table shaping."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


def clean_channel_name(name: object) -> str:
    """Return a stable, non-empty channel name for DataFrame columns."""
    cleaned = "" if name is None else str(name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Unnamed"


def ensure_unique_channel_names(channels: pd.DataFrame) -> pd.DataFrame:
    """Clean channel names and suffix duplicates while keeping order."""
    channels = channels.copy()
    seen: dict[str, int] = {}
    names: list[str] = []

    for raw_name in channels["name"].tolist():
        base = clean_channel_name(raw_name)
        count = seen.get(base, 0)
        seen[base] = count + 1
        names.append(base if count == 0 else f"{base}_{count + 1}")

    channels["name"] = names
    if "unit" in channels.columns:
        channels["unit"] = channels["unit"].map(clean_unit)
    return channels


def clean_unit(unit: object) -> str | None:
    if unit is None or pd.isna(unit):
        return None

    cleaned = str(unit).strip()
    replacements = {
        "��C": "°C",
        "\ufffd\ufffdC": "°C",
    }
    return replacements.get(cleaned, cleaned)


def normalize_to_ipemotion_csv(df: pd.DataFrame, rate: float) -> pd.DataFrame:
    """Match the legacy CSV shape consumed by HB_automation preprocessing."""
    rate_label = int(rate) if float(rate).is_integer() else rate
    df = df.rename(columns={"time_s": f"Time {rate_label}Hz"})

    columns = df.columns.tolist()
    time_col = columns[0]
    df = df[[time_col] + [column for column in columns if column != time_col]]

    # Legacy GUI preprocessing indexes from the last columns, so preserve the
    # two dummy columns used by the old iad_to_csv implementation.
    df[""] = np.nan
    df[" "] = np.nan
    return df
