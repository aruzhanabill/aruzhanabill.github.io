import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from utils import OUTPUT_HZ

import pipeline_2025_26 as _p1
import pipeline_2025_26_b as _p2
import pipeline_2025_26_c as _p3


SESSIONS = [
    {
        "id": "cf_0",
        "type": "Cold Flow",
        "label": "3/15/2026",
        "tz": "America/New_York",
        "start": datetime(2026, 3, 13, 14, 30),
        "window": timedelta(minutes=94),
        "events": {
            5414.5: "Vent Close",
            5439.5: "Fill Relief Crack",
            5443.0: "Fill Relief Full Open",
            5445.6: "Vent Partial Open",
            5452.0: "Run Open + Vent Full Open",
        },
        "pipeline": _p1,
    },
    {
        "id": "cf_1",
        "type": "Cold Flow",
        "label": "3/27/2026",
        "tz": "America/New_York",
        "start": datetime(2026, 3, 27, 14, 0),
        "window": timedelta(minutes=120),
        "events": {},
        "pipeline": _p2,
    },
    {
        "id": "cf_1",
        "type": "Cold Flow",
        "label": "4/3/2026",
        "tz": "America/New_York",
        "start": datetime(2026, 4, 3, 15, 20),
        "window": timedelta(minutes=120),
        "events": {},
        "pipeline": _p3,
    },
]
MAX_POINTS    = 30_000   # overview downsample — fast initial load
CHUNK_SECONDS = 60       # seconds per high-res chunk file
CHUNK_HZ      = 300      # Hz stored in chunks (≈ native load-cell rate)
_CHUNK_STEP   = max(1, OUTPUT_HZ // CHUNK_HZ)  # rows to skip when writing chunks

DATA_DIR = Path("data")

def to_json_safe(series: pd.Series) -> list:
    """Convert a pandas Series to a JSON-safe Python list (NaN → null)."""
    out = []
    for v in series:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        else:
            out.append(round(float(v), 6))
    return out

def main():
    DATA_DIR.mkdir(exist_ok=True)

    cf_sessions: list[dict] = []
    sf_sessions: list[dict] = []

    for sess in SESSIONS:
        print(f"\n{'='*60}")
        print(f"  {sess['type']}  {sess['label']}")
        print(f"{'='*60}")

        pipeline = sess["pipeline"]

        print("  Fetching data from cache...")
        df_full = pipeline.fetch_data(sess["tz"], sess["start"], sess["window"])
        df_full["t_sec"] = (df_full["ts"] - df_full["ts"].min()) / 1e6
        t_max = round(float(df_full["t_sec"].max()), 3)
        print(f"  {len(df_full):,} rows  ·  {t_max:.1f} s")

        # Overview: aggressively downsample for fast initial load
        if len(df_full) > MAX_POINTS:
            step = len(df_full) // MAX_POINTS
            df_overview = df_full.iloc[::step].reset_index(drop=True)
        else:
            df_overview = df_full
        print(f"  Overview: {len(df_overview):,} rows")

        needed_cols: set[str] = set()
        for plot in pipeline.PLOTS:
            cols = plot.columns if isinstance(plot.columns, list) else [plot.columns]
            needed_cols.update(cols)
            needed_cols.update(getattr(plot, "state_columns", []))

        data: dict = {"t_sec": to_json_safe(df_overview["t_sec"])}
        for col in sorted(needed_cols):
            if col in df_overview.columns and pd.api.types.is_numeric_dtype(df_overview[col]):
                data[col] = to_json_safe(df_overview[col])
            else:
                print(f"  Warning: '{col}' missing or non-numeric — skipped")

        plots_meta = [
            {
                "title": p.title,
                "columns": p.columns if isinstance(p.columns, list) else [p.columns],
                "state_columns": getattr(p, "state_columns", []),
            }
            for p in pipeline.PLOTS
        ]

        n_chunks = math.ceil(t_max / CHUNK_SECONDS)
        out = {
            "id":            sess["id"],
            "type":          sess["type"],
            "label":         sess["label"],
            "t_max":         t_max,
            "chunk_seconds": CHUNK_SECONDS,
            "n_chunks":      n_chunks,
            "events":        {str(k): v for k, v in sess["events"].items()},
            "plots":         plots_meta,
            "data":          data,
        }

        path = DATA_DIR / f"{sess['id']}.json"
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))
        size_kb = path.stat().st_size / 1024
        print(f"  Written {path}  ({size_kb:.0f} KB)")

        # High-res chunks: one file per CHUNK_SECONDS, stored at CHUNK_HZ
        chunks_dir = DATA_DIR / f"{sess['id']}_chunks"
        chunks_dir.mkdir(exist_ok=True)
        # df_full at CHUNK_HZ (skip every _CHUNK_STEP rows)
        df_chunk_base = df_full.iloc[::_CHUNK_STEP].reset_index(drop=True)
        for ci in range(n_chunks):
            c_t0 = ci * CHUNK_SECONDS
            c_t1 = (ci + 1) * CHUNK_SECONDS
            mask = (df_chunk_base["t_sec"] >= c_t0) & (df_chunk_base["t_sec"] < c_t1)
            cdf  = df_chunk_base[mask]
            cdata: dict = {"t_sec": to_json_safe(cdf["t_sec"])}
            for col in sorted(needed_cols):
                if col in cdf.columns and pd.api.types.is_numeric_dtype(cdf[col]):
                    cdata[col] = to_json_safe(cdf[col])
            chunk_path = chunks_dir / f"{ci:04d}.json"
            with open(chunk_path, "w") as f:
                json.dump(cdata, f, separators=(",", ":"))
            if (ci + 1) % 20 == 0 or ci == n_chunks - 1:
                print(f"  Chunks: {ci+1}/{n_chunks}", end="\r")
        print(f"  Written {n_chunks} chunks in {chunks_dir}/  ({CHUNK_HZ} Hz)")

        entry = {"id": sess["id"], "label": sess["label"]}
        if sess["type"] == "Cold Flow":
            cf_sessions.append(entry)
        else:
            sf_sessions.append(entry)
    manifest = {"cold_flow": cf_sessions, "static_fire": sf_sessions}
    manifest_path = DATA_DIR / "sessions.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  Written {manifest_path}")

    print("\n" + "="*60)
    print("  Done.")
    print("  Commit the data/ folder and push to deploy:")
    print("    git add data/")
    print("    git commit -m 'update test data'")
    print("    git push")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()