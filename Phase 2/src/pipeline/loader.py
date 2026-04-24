# src/pipeline/loader.py
import os
import glob
import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Columns present in ip_addresses_sample (re-aggregated format).
# n_dest_ip / n_dest_asn / n_dest_port are expanded into sum/average/std.
CESNET_COLUMNS = [
    "id_time",
    "n_flows",
    "n_packets",
    "n_bytes",
    "sum_n_dest_asn",
    "average_n_dest_asn",
    "std_n_dest_asn",
    "sum_n_dest_ports",
    "average_n_dest_ports",
    "std_n_dest_ports",
    "sum_n_dest_ip",
    "average_n_dest_ip",
    "std_n_dest_ip",
    "tcp_udp_ratio_packets",
    "tcp_udp_ratio_bytes",
    "dir_ratio_packets",
    "dir_ratio_bytes",
    "avg_duration",
    "avg_ttl",
]

# Columns that confirm a file is already in CESNET format (header present)
CESNET_MARKER_COLS = {"n_bytes", "n_packets", "n_flows"}

# Minimum samples a series must have to be used
MIN_SERIES_LENGTH = 200


def load_cesnet_sample(
    data_dir:   str,
    signal_col: str            = "n_bytes",
    max_ips:    Optional[int]  = None,
    min_length: int            = MIN_SERIES_LENGTH,
) -> List[Tuple[str, np.ndarray]]:
    """
    Load CESNET ip_addresses_sample CSVs and return normalised time series.

    Returns
    -------
    List of (ip_id, signal_array) where signal_array is float64, zero-mean
    unit-variance normalised.
    """
    csv_files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))

    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in:\n  {data_dir}\n"
            "Make sure DATA_DIR in config.py points to the agg_10_minutes folder\n"
            "inside ip_addresses_sample."
        )

    if max_ips is not None:
        csv_files = csv_files[:max_ips]

    series_list = []
    skipped     = 0

    for fpath in csv_files:
        ip_id = os.path.splitext(os.path.basename(fpath))[0]
        try:
            df = _read_cesnet_csv(fpath)

            if signal_col not in df.columns:
                logger.warning(
                    f"Column '{signal_col}' not in {os.path.basename(fpath)} "
                    f"(columns: {list(df.columns)[:5]}...), skipping."
                )
                skipped += 1
                continue

            raw = df[signal_col].values.astype(np.float64)
            raw = raw[np.isfinite(raw)]

            if len(raw) < min_length:
                skipped += 1
                continue

            series_list.append((ip_id, _normalize(raw)))

        except Exception as e:
            logger.warning(f"Failed to load {os.path.basename(fpath)}: {e}")
            skipped += 1
            continue

    logger.info(
        f"Loaded {len(series_list)} IP series from {data_dir} "
        f"(skipped {skipped}, signal='{signal_col}')"
    )

    if not series_list:
        raise ValueError(
            f"No valid series loaded.\n"
            f"Signal column requested: '{signal_col}'\n"
            f"Min series length required: {min_length}\n"
            f"Directory searched: {data_dir}\n"
            f"Make sure the CSVs contain '{signal_col}' and have >= {min_length} rows."
        )

    return series_list


def _read_cesnet_csv(fpath: str) -> pd.DataFrame:
    """
    Read a single CESNET CSV. Handles:
    - Files with correct header (normal case for ip_addresses_sample)
    - Files without header (assign CESNET_COLUMNS)
    - Windows encoding issues (utf-8 → latin-1 → cp1252 fallback)
    """
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(fpath, encoding=enc)

            # If column count matches but no CESNET marker cols found → no header
            if (df.shape[1] == len(CESNET_COLUMNS)
                    and not CESNET_MARKER_COLS.intersection(df.columns)):
                df = pd.read_csv(
                    fpath, header=None, names=CESNET_COLUMNS, encoding=enc
                )
            return df

        except UnicodeDecodeError:
            continue
        except Exception:
            continue

    # Absolute last resort
    return pd.read_csv(fpath, encoding="utf-8", errors="ignore")


def _normalize(arr: np.ndarray) -> np.ndarray:
    mean = np.mean(arr)
    std  = np.std(arr)
    if std < 1e-10:
        return np.zeros_like(arr)
    return (arr - mean) / std


def get_baseline_segment(
    series: np.ndarray, start: int, length: int
) -> np.ndarray:
    if start + length > len(series):
        raise ValueError(
            f"Segment [{start}:{start+length}] exceeds series length {len(series)}"
        )
    return series[start : start + length].copy()
