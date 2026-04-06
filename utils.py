import hashlib
import io
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, cast

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
from ipywidgets import FloatSlider, Layout, interactive

BASE_URL = "https://csi-fs-pi-data-server.ngrok.io"
CACHE_DIR = "cache"

FETCH_BATCH_MINUTES = 20

# set this to be larger than the frequencies of the individuals dataframes,
# but not to large to conserve compute
OUTPUT_HZ = 1000

PLOT_SAMPLE_COUNT = 1000


def fetch_devices(start: datetime, window: timedelta, *devices: str) -> pd.DataFrame:
    all_data: list[pd.DataFrame] = []

    for device in devices:
        device_data = fetch_device(device, start, window)
        all_data.append(device_data)

    merged = pd.DataFrame(
        {"ts": range(*to_ts_range(start, window), int(1e6 / OUTPUT_HZ))}
    )

    for data in all_data:
        merged = pd.merge_asof(merged, data, on="ts", direction="nearest")

    return merged


@dataclass
class Plot:
    title: str
    columns: str | list[str]
    state_columns: list[str] = field(default_factory=list)


def plot_interactive(df: pd.DataFrame, *plots: Plot):
    def ts_slider(value: Literal["min", "max"]):
        min = df["ts"].min() / 1e6
        max = df["ts"].max() / 1e6
        return FloatSlider(
            min if value == "min" else max,
            min=min,
            max=max,
            step=1,
            continuous_update=False,
            layout=Layout(width="100%"),
        )

    def plot_fn(ts_min_sec: float, ts_max_sec: float):
        print("Min ts (sec):", ts_min_sec)
        print("Max ts (sec):", ts_max_sec)

        ts_min = ts_min_sec * 1e6
        ts_max = ts_max_sec * 1e6

        for plot in plots:
            columns = plot.columns if isinstance(plot.columns, list) else [plot.columns]
            columns = [col for col in columns if col in df.columns and pd.api.types.is_numeric_dtype(df[col])]
            if not columns:
                continue

            plot_df = df[(df["ts"] >= ts_min) & (df["ts"] <= ts_max)]
            # Sample at most 1,000 rows for plotting
            if len(plot_df) > PLOT_SAMPLE_COUNT:
                plot_df = plot_df.sample(n=PLOT_SAMPLE_COUNT).sort_values("ts")
            plot_df.plot(  # type: ignore
                "ts", columns, title=plot.title, figsize=(15, 3), style="."
            )
            plt.show()

    return interactive(
        plot_fn,
        ts_min_sec=ts_slider("min"),
        ts_max_sec=ts_slider("max"),
    )


def get_csv_with_cache(url: str) -> pd.DataFrame:
    url_hash = hashlib.sha256(url.encode()).hexdigest()

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, url_hash + ".csv")

    if os.path.exists(cache_file):
        return pd.read_csv(cache_file)

    req = urllib.request.Request(
        url, headers={"ngrok-skip-browser-warning": "true"}
    )
    with urllib.request.urlopen(req) as r:
        df = pd.read_csv(io.BytesIO(r.read()))

    df.to_csv(cache_file, index=False)
    return df


def to_ts_range(start: datetime, window: timedelta) -> tuple[int, int]:
    start_ts = int(start.timestamp() * 1e6)
    end_ts = start_ts + int(window.total_seconds() * 1e6)
    return start_ts, end_ts


def fetch_device(device: str, start: datetime, window: timedelta) -> pd.DataFrame:
    # limit fetch window to avoid timeouts
    max_window_ts = int(timedelta(minutes=FETCH_BATCH_MINUTES).total_seconds() * 1e6)

    start_ts, end_ts = to_ts_range(start, window)
    cur_start_ts = start_ts
    df = None

    while cur_start_ts <= end_ts:
        cur_end_ts = min(cur_start_ts + max_window_ts, end_ts)
        url = f"{BASE_URL}/export/0/all/{device}/records?&startTs={cur_start_ts}&endTs={cur_end_ts}"
        cur_df = get_csv_with_cache(url)
        df = cur_df if df is None else pd.concat([df, cur_df])
        cur_start_ts += max_window_ts + 1

    df = cast(pd.DataFrame, df)
    assert "ts" in df.columns

    # drop device-internal ts if present, keep server-assigned Unix timestamp
    if "ts.1" in df.columns:
        del df["ts.1"]

    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")

    mapping = {col: f"{device}.{col}" for col in df.columns if col != "ts"}
    df = df.rename(columns=mapping)

    df = df.sort_values(by=["ts"])
    df = df.reset_index(drop=True)

    return df
