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

PLOTS = [
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
    ),
    Plot(
        "[FsScientific1] LOX Tank Transducer",
        ["FsLoxGn2Transducers.oxtank_2"],
    ),
    Plot(
        "[FsScientific1] COPV / GN2 Transducer",
        ["FsLoxGn2Transducers.copv_1"],
    ),
    Plot(
        "[FsScientific1] Press Pilot Transducer",
        ["FsLoxGn2Transducers.pilot_pres"],
    ),
    Plot(
        "[FsScientific2] Injector Transducers",
        ["FsInjectorTransducers.injector_1", "FsInjectorTransducers.injector_2"],
    ),
    Plot(
        "[FsScientific2] Upper CC Transducer",
        ["FsInjectorTransducers.upper_cc"],
    ),
    Plot(
        "[CapFill] Capacitive Fill Sensor",
        ["CapFill.cap_fill_base", "CapFill.cap_fill_actual"],
    ),
    Plot(
        "[LoadCells] Individual Load Cell",
        ["LoadCell1.data", "LoadCell2.data"],
    ),
    Plot("[LoadCells] Load Cell Sum", "thrust"),
]

def fetch_data(tz: str, start: datetime, window: timedelta) -> pd.DataFrame:
    df = fetch_devices(timezone(tz).localize(start), window, *DEVICES)
    return clean_up(df)

def fetch_and_plot_pipeline(tz: str, start: datetime, window: timedelta):
    print("Fetching data...")
    df = fetch_data(tz, start, window)
    print("Loading interactive plot...")
    return plot_interactive(df, *PLOTS)

def clean_up(df: pd.DataFrame) -> pd.DataFrame:
    df["LoadCell1.data"] = -df["LoadCell1.data"]
    df["LoadCell2.data"] = -df["LoadCell2.data"]
    df["thrust"] = df["LoadCell1.data"] + df["LoadCell2.data"]
    df["thrust"] = df["thrust"].rolling(window=10).median()
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