import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import pipeline_2025_26 as _p1
import pipeline_2025_26_b as _p2

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
]
MAX_POINTS = 30_000

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
        df = pipeline.fetch_data(sess["tz"], sess["start"], sess["window"])
        df["t_sec"] = (df["ts"] - df["ts"].min()) / 1e6
        print(f"  {len(df):,} rows  ·  {df['t_sec'].max():.1f} s")
        if len(df) > MAX_POINTS:
            step = len(df) // MAX_POINTS
            df = df.iloc[::step].reset_index(drop=True)
        print(f"  Downsampled to {len(df):,} rows")
        needed_cols: set[str] = set()
        for plot in pipeline.PLOTS:
            cols = plot.columns if isinstance(plot.columns, list) else [plot.columns]
            needed_cols.update(cols)
        data: dict = {"t_sec": to_json_safe(df["t_sec"])}
        for col in sorted(needed_cols):
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                data[col] = to_json_safe(df[col])
            else:
                print(f"  Warning: '{col}' missing or non-numeric — skipped")
        plots_meta = [
            {
                "title": p.title,
                "columns": p.columns if isinstance(p.columns, list) else [p.columns],
            }
            for p in pipeline.PLOTS
        ]

        out = {
            "id":     sess["id"],
            "type":   sess["type"],
            "label":  sess["label"],
            "t_max":  round(float(df["t_sec"].max()), 3),
            "events": {str(k): v for k, v in sess["events"].items()},
            "plots":  plots_meta,
            "data":   data,
        }

        path = DATA_DIR / f"{sess['id']}.json"
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))

        size_kb = path.stat().st_size / 1024
        print(f"  Written {path}  ({size_kb:.0f} KB)")

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