# -*- coding: utf-8 -*-
"""IAD extraction, UTF-16 metadata parsing, and CHA binary conversion."""

from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


XML_SIGNATURES = (
    b"\xff\xfe<\x00?\x00x\x00m\x00l\x00",
    b"\xfe\xff\x00<\x00?\x00x\x00m\x00l",
)


def extract_iad(iad_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Extract a zip-based IPETRONIK .iad file and return extracted paths."""
    iad_path = Path(iad_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(iad_path, "r") as zf:
        zf.extractall(out_dir)

    return list(out_dir.glob("*"))


def find_ird_file(work_dir: str | Path) -> Path:
    ird_files = sorted(Path(work_dir).glob("*.ird"))
    if not ird_files:
        raise FileNotFoundError(f"No .ird file found in {work_dir}")
    return ird_files[0]


def find_cha_file(work_dir: str | Path, channel_id: int | str) -> Path | None:
    """Find a CHA file for a channel id.

    Existing files are normally named like ``1_117.cha``. Some exports may use
    a different first number, so fall back to any ``*_{id}.cha`` match.
    """
    work_dir = Path(work_dir)
    channel_id = str(int(channel_id))

    preferred = work_dir / f"1_{channel_id}.cha"
    if preferred.exists():
        return preferred

    matches = sorted(work_dir.glob(f"*_{channel_id}.cha"))
    return matches[0] if matches else None


def extract_xml_from_ird(ird_path: str | Path, xml_out: str | Path) -> Path:
    """Extract the embedded UTF-16 XML document from an .ird file."""
    ird_path = Path(ird_path)
    xml_out = Path(xml_out)
    data = ird_path.read_bytes()

    start = -1
    for signature in XML_SIGNATURES:
        start = data.find(signature)
        if start >= 0:
            break

    if start < 0:
        raise RuntimeError(f"UTF-16 XML not found in IRD: {ird_path}")

    xml_text = data[start:].decode("utf-16", errors="ignore").strip("\x00\uffff")
    xml_text = _trim_after_root(xml_text)

    xml_out.parent.mkdir(parents=True, exist_ok=True)
    xml_out.write_text(xml_text, encoding="utf-16")
    return xml_out


def parse_channels(xml_path: str | Path) -> pd.DataFrame:
    """Parse channel metadata used for CHA conversion and export."""
    root = ET.parse(xml_path).getroot()
    rows: list[dict] = []

    for idx, channel in enumerate(root.iter("AcquisitionRawFileChannel")):
        params = channel.find("ParameterList")
        if params is None:
            continue

        values = {child.tag: _clean_text(child.text) for child in list(params)}
        channel_id = _to_int(values.get("id"))
        name = values.get("name")

        if channel_id is None or not name:
            continue

        bit_count = _to_int(values.get("bitCount"))
        data_size = _to_int(values.get("dataSizeMax"))
        binary_min = _to_int(values.get("binaryMin"))
        binary_max = _to_int(values.get("binaryMax"))
        physical_min = _to_float(values.get("physicalMin"))
        physical_max = _to_float(values.get("physicalMax"))
        if physical_min is None:
            physical_min = _to_float(values.get("sensorMin"))
        if physical_max is None:
            physical_max = _to_float(values.get("sensorMax"))
        sample_rate = _to_float(values.get("sampleRate"), default=1.0)
        no_value = _parse_no_value(values.get("noValueValue"))

        if bit_count is not None:
            channel_type = "can"
            if binary_min is None:
                binary_min = 0
            if binary_max is None:
                binary_max = (2**bit_count) - 1

            if bit_count <= 8:
                dtype = "uint8"
            elif bit_count <= 16:
                dtype = "uint16"
            else:
                dtype = "uint32"
        else:
            channel_type = "physical"
            if data_size == 2:
                dtype = "int16"
            elif data_size == 4:
                dtype = "float32"
            else:
                dtype = "unknown"

        scale, offset, formula = build_conversion(
            channel_type=channel_type,
            bit_count=bit_count,
            data_size=data_size,
            binary_min=binary_min,
            binary_max=binary_max,
            physical_min=physical_min,
            physical_max=physical_max,
        )

        rows.append(
            {
                "channel_index": idx,
                "id": channel_id,
                "name": name,
                "unit": values.get("physicalUnit") or values.get("sensorUnit"),
                "channel_type": channel_type,
                "sampleRate": sample_rate,
                "dataSizeMax": data_size,
                "bitCount": bit_count,
                "dtype": dtype,
                "binaryMin": binary_min,
                "binaryMax": binary_max,
                "noValueValue": no_value,
                "physicalMin": physical_min,
                "physicalMax": physical_max,
                "scale": scale,
                "offset": offset,
                "conversion_formula": formula,
                "startBit": values.get("startBit"),
                "canId": values.get("canId"),
                "reference": values.get("reference"),
                "signalKey": values.get("signalKey"),
            }
        )

    return pd.DataFrame(rows)


def cha_to_dataframe(
    cha_path: str | Path,
    ch_meta: pd.Series | dict,
    n_samples: int | None = None,
    drop_initial_seconds: float = 0,
) -> pd.DataFrame:
    """Convert one CHA binary file to a two-column time/value DataFrame."""
    meta = ch_meta.to_dict() if hasattr(ch_meta, "to_dict") else dict(ch_meta)
    dtype = meta.get("dtype")

    if meta.get("channel_type") == "can":
        dtype_map = {
            "uint8": np.uint8,
            "uint16": np.uint16,
            "uint32": np.uint32,
        }
        if dtype not in dtype_map:
            raise ValueError(f"Unsupported CAN dtype: {dtype}")
        raw = np.fromfile(cha_path, dtype=dtype_map[dtype]).astype(float)
    else:
        if dtype == "int16":
            raw = np.fromfile(cha_path, dtype="<i2").astype(float)
        elif dtype == "float32":
            raw = np.fromfile(cha_path, dtype="<f4").astype(float)
        else:
            raise ValueError(f"Unsupported physical dtype: {dtype}")

    no_value = meta.get("noValueValue")
    if pd.notna(no_value):
        raw[raw == float(no_value)] = np.nan

    if n_samples is not None:
        raw = raw[:n_samples]

    scale = meta.get("scale")
    offset = meta.get("offset")
    if pd.notna(scale) and pd.notna(offset):
        physical = float(scale) * raw + float(offset)
    else:
        physical = raw

    sample_rate = float(meta.get("sampleRate") or 1)
    time_s = np.arange(len(physical)) / sample_rate

    df = pd.DataFrame({"time_s": time_s, meta["name"]: physical})

    if drop_initial_seconds > 0:
        df = df[df["time_s"] >= drop_initial_seconds].copy()
        df["time_s"] -= drop_initial_seconds
        df.reset_index(drop=True, inplace=True)

    return df


def build_conversion(
    channel_type: str,
    bit_count: int | None,
    data_size: int | None,
    binary_min: int | None,
    binary_max: int | None,
    physical_min: float | None,
    physical_max: float | None,
) -> tuple[float | None, float | None, str]:
    if physical_min is None or physical_max is None:
        return None, None, "raw"

    if channel_type == "can":
        if binary_min is None:
            binary_min = 0
        if binary_max is None and bit_count is not None:
            binary_max = (2**bit_count) - 1
        if binary_max is None or binary_max == binary_min:
            return None, None, "raw"
        scale = (physical_max - physical_min) / (binary_max - binary_min)
        offset = physical_min - scale * binary_min
    else:
        if not data_size:
            return None, None, "raw"
        full_scale = (2 ** (data_size * 8)) - 1
        scale = (physical_max - physical_min) / full_scale
        offset = physical_min

    return scale, offset, f"physical = raw * {scale:g} + {offset:g}"


def _trim_after_root(xml_text: str) -> str:
    end_tag = "</IPEmotionXmlFile>"
    end = xml_text.find(end_tag)
    if end >= 0:
        return xml_text[: end + len(end_tag)]
    return xml_text


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _to_float(value: str | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: str | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value, 0)
    except (TypeError, ValueError):
        return default


def _parse_no_value(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return _to_int(value)
