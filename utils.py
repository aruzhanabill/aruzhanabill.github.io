import hashlib
import io
import os
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

import pandas as pd
import plotly.graph_objects as go
from IPython.display import display
from ipywidgets import HTML, FloatRangeSlider, Layout, VBox

BASE_URL = "https://csi-fs-pi-data-server.ngrok.io"
CACHE_DIR = Path(__file__).parent / "cache"

FETCH_BATCH_MINUTES = 20

# set this to be larger than the frequencies of the individual dataframes,
# but not so large as to conserve compute
OUTPUT_HZ = 1000

# Max points rendered per trace at any zoom level
PLOT_SAMPLE_COUNT = 5000


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


def _ts_sec_to_dt(ts_sec: float) -> pd.Timestamp:
    """Convert a seconds-since-epoch float to an ET-aware Timestamp."""
    return pd.to_datetime(ts_sec * 1e6, unit="us", utc=True).tz_convert(
        "America/New_York"
    )


def _window_sample(df: pd.DataFrame, ts_min_sec: float, ts_max_sec: float) -> pd.DataFrame:
    """
    Filter df to the given time window (in seconds) and uniformly downsample
    to at most PLOT_SAMPLE_COUNT rows.  Narrower windows → fewer rows to skip
    → higher effective resolution automatically.
    """
    ts_min_us = ts_min_sec * 1e6
    ts_max_us = ts_max_sec * 1e6
    window = df[(df["ts"] >= ts_min_us) & (df["ts"] <= ts_max_us)]
    if len(window) > PLOT_SAMPLE_COUNT:
        step = max(1, len(window) // PLOT_SAMPLE_COUNT)
        window = window.iloc[::step]
    return window


def plot_interactive(df: pd.DataFrame, *plots: Plot) -> None:
    # Convert microsecond timestamps to timezone-aware datetimes once
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["ts"], unit="us", utc=True).dt.tz_convert(
        "America/New_York"
    )

    ts_min_sec = float(df["ts"].min() / 1e6)
    ts_max_sec = float(df["ts"].max() / 1e6)

    # Build (FigureWidget, column_list) pairs, skipping any plot with no valid data
    fig_col_pairs: list[tuple[go.FigureWidget, list[str]]] = []

    init_df = _window_sample(df, ts_min_sec, ts_max_sec)

    for plot in plots:
        columns = plot.columns if isinstance(plot.columns, list) else [plot.columns]
        columns = [
            col
            for col in columns
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col])
        ]
        if not columns:
            continue

        is_relay = any("FsState" in col for col in columns)
        line_shape = "hv" if is_relay else "linear"

        fig = go.FigureWidget()

        for col in columns:
            col_data = init_df[["datetime", col]].dropna(subset=[col])
            short_name = col.split(".")[-1]
            fig.add_trace(
                go.Scatter(
                    x=col_data["datetime"].values,
                    y=col_data[col].values,
                    mode="lines",
                    name=short_name,
                    line=dict(shape=line_shape, width=1.5),
                    hovertemplate=(
                        "<b>%{x|%H:%M:%S.%L}</b><br>"
                        + short_name
                        + ": <b>%{y:.4f}</b><extra></extra>"
                    ),
                )
            )

        # Relay plot: vertical legend on right so 8 labels don't crowd the title
        if is_relay:
            legend_cfg = dict(
                orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.01
            )
            right_margin = 160
        else:
            legend_cfg = dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0
            )
            right_margin = 30

        fig.update_layout(
            title=dict(text=plot.title, font=dict(size=13)),
            height=300,
            autosize=True,
            hovermode="x unified",
            xaxis=dict(
                title="Time (ET)",
                type="date",
                tickformat="%H:%M:%S",
                # no per-plot rangeslider — we use the global slider instead
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(title="Value"),
            legend=legend_cfg,
            margin=dict(l=60, r=right_margin, t=50, b=40),
            template="plotly_white",
        )

        fig_col_pairs.append((fig, columns))

    figures = [f for f, _ in fig_col_pairs]

    # ── Global time-range slider ───────────────────────────────────────────────
    # continuous_update=False: re-render fires only on mouse-release, not every
    # drag tick (updating 9 figures × N traces per tick would lag badly)
    slider = FloatRangeSlider(
        value=[ts_min_sec, ts_max_sec],
        min=ts_min_sec,
        max=ts_max_sec,
        step=1.0,
        description="Time range:",
        continuous_update=False,
        readout=False,
        layout=Layout(width="99%"),
        style={"description_width": "90px"},
    )

    dt_fmt = "%H:%M:%S"

    def _label_html(lo: float, hi: float) -> str:
        return (
            f"<span style='font-family:monospace;font-size:12px'>"
            f"{_ts_sec_to_dt(lo).strftime(dt_fmt)}"
            f" &nbsp;→&nbsp; "
            f"{_ts_sec_to_dt(hi).strftime(dt_fmt)}"
            f"</span>"
        )

    label = HTML(value=_label_html(ts_min_sec, ts_max_sec))

    def on_slider_change(change: dict) -> None:
        lo, hi = change["new"]
        dt_lo = _ts_sec_to_dt(lo)
        dt_hi = _ts_sec_to_dt(hi)

        label.value = _label_html(lo, hi)

        # Re-sample the full df for this window — narrower window = higher
        # effective resolution (more of the 5000 points cover less time)
        window_df = _window_sample(df, lo, hi)

        for fig, columns in fig_col_pairs:
            with fig.batch_update():
                for j, col in enumerate(columns):
                    col_data = window_df[["datetime", col]].dropna(subset=[col])
                    fig.data[j].x = col_data["datetime"].values
                    fig.data[j].y = col_data[col].values
                fig.layout.xaxis.range = [dt_lo.isoformat(), dt_hi.isoformat()]

    slider.observe(on_slider_change, names="value")

    display(VBox([slider, label, *figures], layout=Layout(width="100%")))


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
