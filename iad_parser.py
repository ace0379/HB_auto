# -*- coding: utf-8 -*-
"""IAD extraction, UTF-16 metadata parsing, and CHA binary conversion."""

from __future__ import annotations

from pathlib import Path
import struct
import zlib
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


XML_SIGNATURES = (
    b"\xff\xfe<\x00?\x00x\x00m\x00l\x00",
    b"\xfe\xff\x00<\x00?\x00x\x00m\x00l",
)


def extract_iad(iad_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Extract an IPETRONIK .iad file and return extracted paths.

    Most IAD files are normal ZIP containers. Some logger exports contain only
    ZIP local file headers without the central directory, so fall back to a
    local-header extractor when ``zipfile`` rejects the archive.
    """
    iad_path = Path(iad_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(iad_path, "r") as zf:
            zf.extractall(out_dir)
    except zipfile.BadZipFile:
        _extract_iad_from_local_headers(iad_path, out_dir)

    return list(out_dir.glob("*"))


def _extract_iad_from_local_headers(iad_path: Path, out_dir: Path) -> None:
    data = iad_path.read_bytes()
    offset = 0
    extracted = 0

    while True:
        header_pos = data.find(b"PK\x03\x04", offset)
        if header_pos < 0:
            break
        if header_pos + 30 > len(data):
            break

        header = data[header_pos : header_pos + 30]
        _, _, _, method, _, _, _, compressed_size, _, name_len, extra_len = struct.unpack("<IHHHHHIIIHH", header)
        name_start = header_pos + 30
        name_end = name_start + name_len
        payload_start = name_end + extra_len
        payload_end = payload_start + compressed_size
        if name_end > len(data) or payload_end > len(data):
            break

        raw_name = data[name_start:name_end].decode("utf-8", errors="replace")
        target = _safe_extract_path(out_dir, raw_name)
        payload = data[payload_start:payload_end]

        if method == 0:
            content = payload
        elif method == 8:
            content = zlib.decompress(payload, -zlib.MAX_WBITS)
        else:
            raise zipfile.BadZipFile(f"Unsupported IAD local-header compression method: {method}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        extracted += 1
        offset = payload_end

    if extracted == 0:
        raise zipfile.BadZipFile(f"File is not a zip file: {iad_path}")


def _safe_extract_path(out_dir: Path, member_name: str) -> Path:
    target = (out_dir / member_name).resolve()
    root = out_dir.resolve()
    if root != target and root not in target.parents:
        raise zipfile.BadZipFile(f"Unsafe IAD member path: {member_name}")
    return target


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
        data_type = _to_int(values.get("dataType"))
        scale_factor = _to_float(values.get("scaleFactor"))
        scale_base = _to_float(values.get("scaleBase"), default=0.0)
        value_count = _to_int(values.get("valueCountX"))

        is_media_channel = _is_media_channel(name, values, data_type)

        if is_media_channel:
            channel_type = "media"
            dtype = "media"
            scale, offset, formula = None, None, "media"
        elif bit_count is not None:
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
            scale, offset, formula = build_conversion(
                channel_type=channel_type,
                bit_count=bit_count,
                data_size=data_size,
                binary_min=binary_min,
                binary_max=binary_max,
                physical_min=physical_min,
                physical_max=physical_max,
            )
        elif data_size is not None:
            channel_type = "physical"
            if data_size == 2:
                dtype = _dtype_from_data_type(data_type)
                if dtype not in {"int16", "uint16"}:
                    dtype = "int16"
            elif data_size == 4:
                dtype = _dtype_from_data_type(data_type)
                if dtype != "float32":
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
            if dtype == "int16" and scale is not None and physical_min is not None:
                raw_min = np.iinfo(np.int16).min
                offset = physical_min - scale * raw_min
                formula = f"physical = (raw - {raw_min}) * {scale:g} + {physical_min:g}"
        elif data_type is not None and scale_factor is not None:
            channel_type = "scaled_physical"
            dtype = _dtype_from_data_type(data_type)
            scale = scale_factor
            offset = scale_base
            formula = f"physical = raw * {scale:g} + {offset:g}"
        else:
            channel_type = "physical"
            dtype = "unknown"
            scale, offset, formula = None, None, "raw"
        rows.append(
            {
                "channel_index": idx,
                "id": channel_id,
                "name": name,
                "unit": values.get("physicalUnit") or values.get("sensorUnit"),
                "channel_type": channel_type,
                "sampleRate": sample_rate,
                "dataSizeMax": data_size,
                "dataType": data_type,
                "valueCountX": value_count,
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

    time_s = None
    if meta.get("channel_type") == "can":
        dtype_map = {
            "uint8": np.uint8,
            "uint16": np.uint16,
            "uint32": np.uint32,
        }
        if dtype not in dtype_map:
            raise ValueError(f"Unsupported CAN dtype: {dtype}")
        raw = np.fromfile(cha_path, dtype=dtype_map[dtype]).astype(float)
    elif meta.get("channel_type") == "scaled_physical":
        raw, time_s = _read_scaled_physical_cha(cha_path, dtype, meta)
        raw = raw.astype(float)
    else:
        raw = _read_physical_cha(cha_path, dtype).astype(float)

    no_value = meta.get("noValueValue")
    if pd.notna(no_value):
        raw[raw == float(no_value)] = np.nan
        if meta.get("channel_type") == "scaled_physical" and float(no_value) == 128.0:
            raw[raw == float(np.iinfo(np.int16).min)] = np.nan
    if n_samples is not None:
        raw = raw[:n_samples]

    scale = meta.get("scale")
    offset = meta.get("offset")
    if pd.notna(scale) and pd.notna(offset):
        physical = float(scale) * raw + float(offset)
    else:
        physical = raw

    if time_s is None:
        sample_rate = float(meta.get("sampleRate") or 1)
        time_s = np.arange(len(physical)) / sample_rate

    df = pd.DataFrame({"time_s": time_s, meta["name"]: physical})

    if drop_initial_seconds > 0:
        keep = df["time_s"].isna() | (df["time_s"] >= drop_initial_seconds)
        df = df[keep].copy()
        df.loc[df["time_s"].notna(), "time_s"] -= drop_initial_seconds
        df.reset_index(drop=True, inplace=True)

    return df



def _read_physical_cha(cha_path: str | Path, dtype: str) -> np.ndarray:
    dtype_map = {
        "int16": np.dtype("<i2"),
        "uint16": np.dtype("<u2"),
        "float32": np.dtype("<f4"),
    }
    if dtype not in dtype_map:
        raise ValueError(f"Unsupported physical dtype: {dtype}")

    np_dtype = dtype_map[dtype]
    data = Path(cha_path).read_bytes()
    if len(data) > 8 and (len(data) - 8) % np_dtype.itemsize == 0:
        data = data[8:]
    return np.frombuffer(data, dtype=np_dtype).copy()


def _read_scaled_physical_cha(cha_path: str | Path, dtype: str, meta: dict) -> tuple[np.ndarray, np.ndarray | None]:
    dtype_map = {
        "uint8": np.dtype("u1"),
        "uint16": np.dtype("<u2"),
        "int16": np.dtype("<i2"),
        "float32": np.dtype("<f4"),
    }
    if dtype not in dtype_map:
        raise ValueError(f"Unsupported scaled physical dtype: {dtype}")

    np_dtype = dtype_map[dtype]
    data = Path(cha_path).read_bytes()
    value_count = meta.get("valueCountX")
    value_count = int(value_count) if pd.notna(value_count) else None

    for candidate_dtype in _scaled_physical_record_dtypes(np_dtype):
        record = _try_read_timestamped_records(data, candidate_dtype, value_count)
        if record is not None:
            return record

    if value_count is not None:
        expected_bytes = value_count * np_dtype.itemsize
        extra_bytes = len(data) - expected_bytes
        if extra_bytes >= 0:
            raw = np.frombuffer(data[extra_bytes:], dtype=np_dtype)[:value_count]
            return raw.copy(), None

    return np.frombuffer(data, dtype=np_dtype).copy(), None


def _scaled_physical_record_dtypes(np_dtype: np.dtype) -> list[np.dtype]:
    candidates = [np_dtype, np.dtype("<i2"), np.dtype("<u2"), np.dtype("u1"), np.dtype("<f4")]
    unique: list[np.dtype] = []
    for candidate in candidates:
        if all(candidate != existing for existing in unique):
            unique.append(candidate)
    return unique


def _try_read_timestamped_records(
    data: bytes,
    np_dtype: np.dtype,
    value_count: int | None,
) -> tuple[np.ndarray, np.ndarray | None] | None:
    record_size = 8 + np_dtype.itemsize
    if value_count is not None:
        if len(data) != value_count * record_size:
            return None
        count = value_count
    else:
        if len(data) < record_size * 2 or len(data) % record_size != 0:
            return None
        count = len(data) // record_size

    record_dtype = np.dtype([("time_ticks", "<u8"), ("raw", np_dtype)])
    records = np.frombuffer(data, dtype=record_dtype, count=count)
    ticks = records["time_ticks"].astype(float)
    diffs = np.diff(ticks)
    positive_diffs = diffs[diffs > 0]
    if len(positive_diffs) == 0 or len(positive_diffs) < max(1, int(len(diffs) * 0.8)):
        return None

    step_s = float(np.median(positive_diffs) / 10_000_000.0)
    if not np.isfinite(step_s) or step_s <= 0 or step_s > 3600:
        return None

    invalid_ticks = ticks >= float(np.iinfo(np.int64).max)
    valid_ticks = ticks[~invalid_ticks]
    if len(valid_ticks) == 0:
        return None

    time_s = np.full(len(records), np.nan, dtype=float)
    time_s[~invalid_ticks] = (valid_ticks - valid_ticks[0]) / 10_000_000.0
    raw = records["raw"].copy()
    if np.issubdtype(raw.dtype, np.signedinteger):
        raw[invalid_ticks] = np.iinfo(raw.dtype).min
    return raw, time_s


def _is_media_channel(name: str, values: dict, data_type: int | None) -> bool:
    media_text = " ".join(
        str(value or "")
        for value in (name, values.get("comment"), values.get("dataFile"), values.get("reference"))
    ).lower()
    return data_type in {4098} or "video" in media_text or "image" in media_text or "webcam" in media_text

def _dtype_from_data_type(data_type: int | None) -> str:
    return {
        1: "uint8",
        2: "int16",
        3: "uint16",
        4: "float32",
    }.get(data_type, "unknown")


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
        parsed = int(value, 16)
    except ValueError:
        parsed = _to_int(value)
    if parsed is None:
        return None
    if parsed > np.iinfo(np.uint64).max:
        return None
    return parsed