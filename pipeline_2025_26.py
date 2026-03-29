from datetime import datetime, timedelta

import pandas as pd
from pytz import timezone

from utils import Plot, fetch_devices, plot_interactive

DEVICES = [
    "FsState",
    "FsLoxGn2Transducers",
    "FsInjectorTransducers",
    "CapFill",
    "LoadCell1",
    "LoadCell2",
]

_RUN     = ["state_run"]
_RUN_LOX = ["state_run", "state_lox_fill_only"]
_RUN_GN2 = ["state_run", "state_gn2_fill_only"]

PLOTS = [
    # ── FsRelays node ─────────────────────────────────────────────────────
    Plot(
        "[FsRelays] Relay & E-Reg States (Even=Off, Odd=On)",
        [
            "FsState.gn2_fill",
            "FsState.depress",
            "FsState.press_pilot",
            "FsState.run",
            "FsState.lox_fill",
            "FsState.lox_disconnect",
            "FsState.igniter",
            "FsState.ereg_power",
            "FsLoxGn2Transducers.ereg_closed",
            "FsLoxGn2Transducers.ereg_stage_1",
            "FsLoxGn2Transducers.ereg_stage_2",
        ],
        state_columns=_RUN,
    ),
    Plot(
        "[FsScientific1] E-Reg Angle",
        ["FsLoxGn2Transducers.current_angle"],
        state_columns=["ereg_state_closed", "ereg_state_stage1", "ereg_state_stage2", "state_run"],
    ),
    # ── FsScientific1 node ────────────────────────────────────────────────
    Plot(
        "[FsScientific1] LOX Tank Transducer",
        ["FsLoxGn2Transducers.oxtank_2"],
        state_columns=_RUN,
    ),
    Plot(
        "[FsScientific1] COPV / GN2 Transducer",
        ["FsLoxGn2Transducers.copv_1"],
        state_columns=_RUN_GN2,
    ),
    Plot(
        "[FsScientific1] Press Pilot Transducer",
        ["FsLoxGn2Transducers.pilot_pres"],
        state_columns=_RUN,
    ),
    # ── FsScientific2 node ────────────────────────────────────────────────
    Plot(
        "[FsScientific2] Injector Transducers",
        ["FsInjectorTransducers.injector_1", "FsInjectorTransducers.injector_2"],
        state_columns=_RUN,
    ),
    Plot(
        "[FsScientific2] Upper CC Transducer",
        ["FsInjectorTransducers.upper_cc"],
        state_columns=_RUN,
    ),
    # ── CapFill node ──────────────────────────────────────────────────────
    Plot(
        "[CapFill] Capacitive Fill Sensor",
        ["CapFill.cap_fill_base", "CapFill.cap_fill_actual"],
        state_columns=_RUN,
    ),
    # ── Load Cells ────────────────────────────────────────────────────────
    Plot(
        "[LoadCells] Individual Load Cell",
        ["LoadCell1.data", "LoadCell2.data"],
        state_columns=_RUN_LOX,
    ),
    Plot("[LoadCells] Load Cell Sum", "thrust", state_columns=_RUN_LOX),
]


def fetch_data(tz: str, start: datetime, window: timedelta) -> pd.DataFrame:
    """Fetch and clean data; returns the processed DataFrame."""
    df = fetch_devices(timezone(tz).localize(start), window, *DEVICES)
    return clean_up(df)


def fetch_and_plot_pipeline(tz: str, start: datetime, window: timedelta):
    """Jupyter-notebook entrypoint: fetch, clean, and display interactive plots."""
    print("Fetching data...")
    df = fetch_data(tz, start, window)
    print("Loading interactive plot...")
    return plot_interactive(df, *PLOTS)


def clean_up(df: pd.DataFrame) -> pd.DataFrame:
    # load cell data is flipped
    df["LoadCell1.data"] = -df["LoadCell1.data"]
    df["LoadCell2.data"] = -df["LoadCell2.data"]

    # sum and clean up load cell data
    df["thrust"] = df["LoadCell1.data"] + df["LoadCell2.data"]
    df["thrust"] = df["thrust"].rolling(window=10).median()

    # preserve raw booleans before stacking (used for background highlights)
    for raw_col, new_col in [
        ("FsLoxGn2Transducers.ereg_closed",  "ereg_state_closed"),
        ("FsLoxGn2Transducers.ereg_stage_1", "ereg_state_stage1"),
        ("FsLoxGn2Transducers.ereg_stage_2", "ereg_state_stage2"),
    ]:
        if raw_col in df.columns:
            df[new_col] = df[raw_col].fillna(False).astype(float)

    run_on      = df["FsState.run"].fillna(False).astype(bool)      if "FsState.run"      in df.columns else pd.Series(False, index=df.index)
    lox_fill_on = df["FsState.lox_fill"].fillna(False).astype(bool) if "FsState.lox_fill" in df.columns else pd.Series(False, index=df.index)
    gn2_fill_on = df["FsState.gn2_fill"].fillna(False).astype(bool) if "FsState.gn2_fill" in df.columns else pd.Series(False, index=df.index)
    df["state_run"]           = run_on.astype(float)
    df["state_lox_fill_only"] = (~run_on & lox_fill_on).astype(float)
    df["state_gn2_fill_only"] = (~run_on & gn2_fill_on).astype(float)

    # convert boolean relay/ereg states to stacked integers
    for i, col in enumerate(
        [
            "FsState.gn2_fill",
            "FsState.depress",
            "FsState.press_pilot",
            "FsState.run",
            "FsState.lox_fill",
            "FsState.lox_disconnect",
            "FsState.igniter",
            "FsState.ereg_power",
            "FsLoxGn2Transducers.ereg_closed",
            "FsLoxGn2Transducers.ereg_stage_1",
            "FsLoxGn2Transducers.ereg_stage_2",
        ]
    ):
        if col in df.columns:
            df[col] = 2 * i + df[col].fillna(False).astype(int)

    return df
