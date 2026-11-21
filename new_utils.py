import hashlib
import io
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast

import matplotlib.pyplot as plt
import pandas as pd
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

def plot_interactive(df: pd.DataFrame, *plots: Plot, events: dict[float, str] | None = None):
    # 1. Calculate relative time on the WHOLE dataset first!
    if "time_sec" not in df.columns:
        df["time_sec"] = (df["ts"] - df["ts"].min()) / 1e6

    def ts_slider(value: Literal["min", "max"]):
        min_val = df["time_sec"].min()
        max_val = df["time_sec"].max()
        return FloatSlider(
            min_val if value == "min" else max_val,
            min=min_val,
            max=max_val,
            step=1,
            description=f"Time {value.capitalize()} (s):",
            continuous_update=False,
            layout=Layout(width="100%"),
        )

    def plot_fn(ts_min_sec: float, ts_max_sec: float):
        for plot in plots:
            columns = plot.columns if isinstance(plot.columns, list) else [plot.columns]
            columns = [col for col in columns if col in df.columns and pd.api.types.is_numeric_dtype(df[col])]
            if not columns:
                continue

            plot_df = df[(df["time_sec"] >= ts_min_sec) & (df["time_sec"] <= ts_max_sec)]
            
            if len(plot_df) > PLOT_SAMPLE_COUNT:
                plot_df = plot_df.sample(n=PLOT_SAMPLE_COUNT).sort_values("time_sec")
            
            # Draw the basic plot
            ax = plot_df.plot(
                x="time_sec", y=columns, title=plot.title, figsize=(15, 3), style="."
            )
            
            # --- NEW: Draw the event lines ---
            if events:
                # Get the top of the Y-axis so we know where to place our text
                ymin, ymax = ax.get_ylim() 
                
                for event_time, event_name in events.items():
                    # Only draw the line if the event happens within our current slider window!
                    if ts_min_sec <= event_time <= ts_max_sec:
                        # Draw a red dashed vertical line
                        plt.axvline(x=event_time, color='red', linestyle='--', alpha=0.7)
                        
                        # Add the text label slightly below the top of the graph
                        plt.text(
                            event_time, 
                            ymax - (ymax - ymin) * 0.05, # 5% down from the top
                            f" {event_name}", 
                            color='red', 
                            rotation=90, 
                            verticalalignment='top'
                        )
            # ---------------------------------
            
            plt.xlabel("Time from start of test (seconds)")
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

    if "ts.1" in df.columns:
        del df["ts.1"]

    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")

    mapping = {col: f"{device}.{col}" for col in df.columns if col != "ts"}
    df = df.rename(columns=mapping)

    df = df.sort_values(by=["ts"])
    df = df.reset_index(drop=True)

    return df