"""
eda_trends.py — Day 16: Trend & Seasonality Analysis
======================================================
Phase 1 | Sub-phase 1.4 — Python EDA | Day 16 of 35

PURPOSE
-------
Connect to data/manufacturing.db, load time-series sensor and production data
using pandas, and use Matplotlib/Seaborn to generate and save three diagnostic
visualisations to data/processed/plots/.

PLOTS GENERATED
---------------
  Plot 1 — rolling_avg_sensor_trends.png
    Multi-axis line chart: 7-day and 14-day rolling averages of Gearbox
    vibration (mm/s RMS) and Motor Housing temperature (°C) over the full
    365-day simulated window. Highlights progressive degradation ramps and
    cascade propagation onset visually.

  Plot 2 — shift_oee_seasonality.png
    Seasonality boxplot: OEE (%) and its three component factors (A%, P%, Q%)
    stratified by shift label (DAY / SWING / NIGHT). Reveals daily cyclical
    patterns — whether the NIGHT shift consistently underperforms, for example.

  Plot 3 — downtime_vs_failures_stacked.png
    Stacked time-series area chart: daily total downtime (by category) versus
    failure event markers from failure_log. Aligns downtime duration accumulation
    with discrete failure timestamps to show cause-and-effect lag.

LOCKED DECISIONS (Day 16)
--------------------------
- Rolling window sizes: 7-day and 14-day.
    7-day captures week-level degradation ramps.
    14-day smooths weekly noise while preserving monthly trends.
    Both windows use min_periods=1 so that early and late boundary days are
    included (avoids leading/trailing NaN strips in the plot).
- Sensor selection: Gearbox vibration (sensor_id=51) and Motor Housing
  temperature (sensor_id=31) are the two "canary" channels: (a) Gearbox
  vibration directly tracks gear-tooth pitting; (b) Motor Housing temperature
  drives the Arrhenius acceleration factor. Both channels showed the highest
  inter-component correlation (r≈0.99) in Day 15 EDA.
- OEE re-computation in Python (not from a pre-existing column): computed
  fresh from production_shifts + downtime_events + production_counts using
  the locked A=1−(downtime/planned), P=MIN(1,(ICT×units)/run_time),
  Q=good/total formula chain (Day 2 decision). This avoids any dependency
  on a cached OEE column that may have drift.
- Timestamp parsing: pd.to_datetime(df['ts']) with utc=False (data has no
  timezone offset). Date floor via .dt.date or .dt.floor('D') for daily
  aggregation.
- Figure DPI: 150 for plot files (good screen/PDF quality, ≤4 MB per image).
- Seaborn theme: 'darkgrid' for boxplots (grid aids quartile reading),
  Matplotlib default style with custom palette for rolling-average lines.
- Output directory: data/processed/plots/ — created by this script if absent.

PANDAS DATETIME HANDLING (locked Day 16)
-----------------------------------------
  pd.to_datetime(df['ts'])                      — parse ISO 8601 strings to Timestamps
  df['date'] = df['ts'].dt.normalize()          — floor to midnight (day resolution)
  df.set_index('ts').resample('D').mean()       — daily resampling for rolling window
  rolling(window=7, min_periods=1).mean()       — 7-day rolling mean; min_periods=1
  rolling(window=14, min_periods=1).mean()      — 14-day rolling mean
  df.groupby('shift_label')                     — shift-based stratification

REFERENCES
----------
  Day 15 CONTEXT.md — Gearbox_vibration ↔ Motor Housing_vibration r=+0.9954
  Day 14 CONTEXT.md — Sensor domain: skew=+2.80, leptokurtic (vibration)
  Day 11 CONTEXT.md — OEE formula chain; shift_label ∈ {DAY, SWING, NIGHT}
  Day  9 CONTEXT.md — sensor_readings schema (ts, value, sensor_id, component_id)
  Day  2 CONTEXT.md — OEE = A × P × Q; downtime_category taxonomy
  ISO 10816-3        — vibration zone thresholds (alarm=4.5, danger=7.1 mm/s)
"""

import os
import sqlite3
import warnings

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

DB_PATH = os.path.join("data", "manufacturing.db")
OUTPUT_DIR = os.path.join("data", "processed", "plots")

# Rolling window sizes (days)
WINDOW_7D = 7
WINDOW_14D = 14

# Sensor IDs (from sql/seed.sql — Day 4 locked values)
SENSOR_GEARBOX_VIBRATION = 51      # vibration, mm/s RMS
SENSOR_MOTOR_TEMP = 31             # temperature, degC

# ISO 10816-3 vibration alarm/danger thresholds
VIB_ALARM = 4.5   # mm/s RMS — Zone C
VIB_DANGER = 7.1  # mm/s RMS — Zone D

# Motor Housing temperature thresholds (IEC 60085 Class B / F)
TEMP_ALARM = 130.0   # °C
TEMP_DANGER = 155.0  # °C

# Figure parameters
DPI = 150
PALETTE = {
    "7d_vib":  "#E8734A",   # warm orange — Gearbox vibration 7-day
    "14d_vib": "#C0392B",   # deep red    — Gearbox vibration 14-day
    "7d_temp": "#3B82F6",   # azure blue  — Motor Housing temp 7-day
    "14d_temp": "#1E3A8A",  # navy        — Motor Housing temp 14-day
}

# Shift colours for seasonality boxplot
SHIFT_PALETTE = {"DAY": "#F59E0B", "SWING": "#6366F1", "NIGHT": "#1E293B"}

# Downtime category stacking colours
DOWNTIME_COLOURS = {
    "unplanned_failure":  "#DC2626",
    "cascade_upstream":   "#F97316",
    "planned_maintenance": "#16A34A",
    "idle":               "#64748B",
    "changeover":         "#A855F7",
}

warnings.filterwarnings("ignore", category=UserWarning)


# ---------------------------------------------------------------------------
# HELPER — DATABASE CONNECTION
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open SQLite connection with FK enforcement (locked Day 14 pattern)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# HELPER — ENSURE OUTPUT DIRECTORY
# ---------------------------------------------------------------------------

def _ensure_output_dir() -> None:
    """Create data/processed/plots/ if it does not already exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[eda_trends] Output directory ready: {OUTPUT_DIR}")


# ---------------------------------------------------------------------------
# DATA LOADERS
# ---------------------------------------------------------------------------

def load_sensor_timeseries(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load daily-averaged sensor values for Gearbox vibration and
    Motor Housing temperature.

    Returns
    -------
    pd.DataFrame with columns:
        date          — daily period (datetime64[ns], midnight-normalised)
        gearbox_vib   — mean Gearbox vibration reading for the day (mm/s RMS)
        motor_temp    — mean Motor Housing temperature reading for the day (°C)
    """
    sql = """
        SELECT
            sr.ts,
            sr.sensor_id,
            sr.value
        FROM sensor_readings sr
        WHERE sr.sensor_id IN (?, ?)
        ORDER BY sr.ts
    """
    df = pd.read_sql_query(sql, conn, params=(SENSOR_GEARBOX_VIBRATION, SENSOR_MOTOR_TEMP))

    # Parse timestamps
    df["ts"] = pd.to_datetime(df["ts"])
    df["date"] = df["ts"].dt.normalize()   # floor to midnight — locked Day 16 pattern

    # Pivot: one row per date, one column per sensor
    pivot = (
        df.groupby(["date", "sensor_id"])["value"]
        .mean()
        .unstack("sensor_id")
    )
    pivot.columns.name = None
    pivot = pivot.rename(columns={
        SENSOR_GEARBOX_VIBRATION: "gearbox_vib",
        SENSOR_MOTOR_TEMP:        "motor_temp",
    })
    pivot = pivot.sort_index()
    return pivot


def load_shift_oee(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Compute per-shift OEE and its three factors (A, P, Q) by joining
    production_shifts, downtime_events, and production_counts.

    Formula (Day 2 locked):
        A = 1 - (total_unplanned_downtime_min / planned_duration_min)
        P = MIN(1.0, (ICT × total_units) / run_time_min)   where run_time = planned - downtime
        Q = good_units / total_units
        OEE = A × P × Q

    Returns
    -------
    pd.DataFrame with columns:
        shift_id, component_id, shift_date, shift_label,
        A_pct, P_pct, Q_pct, OEE_pct   (all ×100, i.e. percentages)
    """
    # --- Downtime aggregation per shift (split unplanned vs planned_maintenance) ---
    downtime_sql = """
        SELECT
            shift_id,
            SUM(CASE WHEN downtime_category != 'planned_maintenance' THEN duration_min ELSE 0 END) AS unplanned_downtime_min,
            SUM(CASE WHEN downtime_category = 'planned_maintenance' THEN duration_min ELSE 0 END) AS planned_maint_min
        FROM downtime_events
        GROUP BY shift_id
    """
    dt_df = pd.read_sql_query(downtime_sql, conn)

    # --- Production counts per shift ---
    counts_sql = """
        SELECT
            shift_id,
            total_units,
            good_units,
            ideal_cycle_time_min
        FROM production_counts
    """
    counts_df = pd.read_sql_query(counts_sql, conn)

    # --- Shifts master ---
    shifts_sql = """
        SELECT
            shift_id,
            component_id,
            shift_date,
            shift_label,
            planned_duration_min
        FROM production_shifts
    """
    shifts_df = pd.read_sql_query(shifts_sql, conn)
    shifts_df["shift_date"] = pd.to_datetime(shifts_df["shift_date"])

    # Merge
    merged = (
        shifts_df
        .merge(dt_df, on="shift_id", how="left")
        .merge(counts_df, on="shift_id", how="left")
    )
    merged["unplanned_downtime_min"] = merged["unplanned_downtime_min"].fillna(0.0)
    merged["planned_maint_min"] = merged["planned_maint_min"].fillna(0.0)

    # Compute factors
    planned_production_time = merged["planned_duration_min"] - merged["planned_maint_min"]
    
    merged["A"] = (planned_production_time - merged["unplanned_downtime_min"]) / planned_production_time.replace(0, np.nan)
    merged["A"] = merged["A"].clip(0.0, 1.0)

    run_time = planned_production_time - merged["unplanned_downtime_min"]
    merged["P"] = (merged["ideal_cycle_time_min"] * merged["total_units"]) / run_time.replace(0, np.nan)
    merged["P"] = merged["P"].clip(0.0, 1.0)

    merged["Q"] = merged["good_units"] / merged["total_units"].replace(0, np.nan)
    merged["Q"] = merged["Q"].clip(0.0, 1.0)

    merged["OEE"] = merged["A"] * merged["P"] * merged["Q"]

    # Convert to percentages
    for col in ("A", "P", "Q", "OEE"):
        merged[f"{col}_pct"] = (merged[col] * 100).round(2)

    return merged[["shift_id", "component_id", "shift_date", "shift_label",
                   "A_pct", "P_pct", "Q_pct", "OEE_pct"]]


def load_downtime_and_failures(conn: sqlite3.Connection) -> tuple:
    """
    Load daily downtime totals by category, and failure event timestamps
    from failure_log.

    Returns
    -------
    daily_dt : pd.DataFrame
        Columns: date (DatetimIndex), one column per downtime_category
    failure_df : pd.DataFrame
        Columns: t_failure_abs, component_name (from join to components)
    """
    # Daily downtime by category — join production_shifts to get the date
    downtime_sql = """
        SELECT
            DATE(ps.shift_date) AS shift_date,
            de.downtime_category,
            SUM(de.duration_min) AS total_min
        FROM downtime_events de
        JOIN production_shifts ps ON de.shift_id = ps.shift_id
        GROUP BY DATE(ps.shift_date), de.downtime_category
        ORDER BY shift_date
    """
    dt_raw = pd.read_sql_query(downtime_sql, conn)
    dt_raw["shift_date"] = pd.to_datetime(dt_raw["shift_date"])

    # Pivot: rows=date, columns=category (zero-fill missing)
    daily_dt = dt_raw.pivot_table(
        index="shift_date",
        columns="downtime_category",
        values="total_min",
        aggfunc="sum",
        fill_value=0.0,
    )
    daily_dt.columns.name = None
    daily_dt = daily_dt.sort_index()

    # Failure events — use downtime_events.start_ts WHERE category='unplanned_failure'
    # (failure_log.t_failure_abs is NULL in this DB build — see Day 11 CONTEXT.md note)
    failure_sql = """
        SELECT
            de.start_ts,
            de.component_name,
            de.failure_mode,
            de.duration_min
        FROM downtime_events de
        WHERE de.downtime_category = 'unplanned_failure'
        ORDER BY de.start_ts
    """
    failure_df = pd.read_sql_query(failure_sql, conn)
    failure_df["failure_datetime"] = pd.to_datetime(failure_df["start_ts"])

    return daily_dt, failure_df


# ---------------------------------------------------------------------------
# PLOT 1 — Rolling Average Sensor Degradation Trends
# ---------------------------------------------------------------------------

def plot_rolling_sensor_trends(sensor_df: pd.DataFrame) -> str:
    """
    Generate Plot 1: multi-axis line chart of 7-day and 14-day rolling averages
    for Gearbox vibration and Motor Housing temperature.

    Layout: Two y-axes on a single Axes via twinx().
    Left  y-axis: Gearbox vibration (mm/s RMS) — ISO alarm/danger hlines.
    Right y-axis: Motor Housing temperature (°C) — IEC alarm/danger hlines.

    Returns path to saved PNG.
    """
    path = os.path.join(OUTPUT_DIR, "rolling_avg_sensor_trends.png")

    # Compute rolling averages (min_periods=1 — no leading NaN strip)
    roll7_vib  = sensor_df["gearbox_vib"].rolling(WINDOW_7D,  min_periods=1).mean()
    roll14_vib = sensor_df["gearbox_vib"].rolling(WINDOW_14D, min_periods=1).mean()
    roll7_temp  = sensor_df["motor_temp"].rolling(WINDOW_7D,  min_periods=1).mean()
    roll14_temp = sensor_df["motor_temp"].rolling(WINDOW_14D, min_periods=1).mean()

    # --- Figure setup ---
    fig, ax1 = plt.subplots(figsize=(16, 6), dpi=DPI)
    ax2 = ax1.twinx()

    dates = sensor_df.index.to_pydatetime()

    # --- Vibration traces (left axis) ---
    ax1.plot(dates, roll7_vib,  color=PALETTE["7d_vib"],  lw=1.8,
             label="Gearbox Vib — 7-day avg",  zorder=4)
    ax1.plot(dates, roll14_vib, color=PALETTE["14d_vib"], lw=2.5, ls="--",
             label="Gearbox Vib — 14-day avg", zorder=4)

    # ISO 10816-3 zone boundaries
    ax1.axhline(VIB_ALARM,  color="#F97316", lw=1.0, ls=":",
                label=f"ISO Alarm {VIB_ALARM} mm/s",  alpha=0.85)
    ax1.axhline(VIB_DANGER, color="#DC2626", lw=1.0, ls=":",
                label=f"ISO Danger {VIB_DANGER} mm/s", alpha=0.85)

    ax1.set_ylabel("Gearbox Vibration (mm/s RMS)", color=PALETTE["14d_vib"], fontsize=11)
    ax1.tick_params(axis="y", labelcolor=PALETTE["14d_vib"])
    ax1.set_ylim(bottom=0)

    # --- Temperature traces (right axis) ---
    ax2.plot(dates, roll7_temp,  color=PALETTE["7d_temp"],  lw=1.8,
             label="Motor Housing Temp — 7-day avg",  zorder=3)
    ax2.plot(dates, roll14_temp, color=PALETTE["14d_temp"], lw=2.5, ls="--",
             label="Motor Housing Temp — 14-day avg", zorder=3)

    ax2.axhline(TEMP_ALARM,  color="#0EA5E9", lw=1.0, ls=":",
                label=f"Temp Alarm {TEMP_ALARM}°C",  alpha=0.85)
    ax2.axhline(TEMP_DANGER, color="#1E3A8A", lw=1.0, ls=":",
                label=f"Temp Danger {TEMP_DANGER}°C", alpha=0.85)

    ax2.set_ylabel("Motor Housing Temperature (°C)", color=PALETTE["14d_temp"], fontsize=11)
    ax2.tick_params(axis="y", labelcolor=PALETTE["14d_temp"])

    # --- X-axis formatting ---
    ax1.set_xlabel("Date", fontsize=11)
    ax1.xaxis.set_major_locator(mticker.MaxNLocator(12))
    fig.autofmt_xdate(rotation=30, ha="right")

    # --- Combined legend ---
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2,
               loc="upper left", fontsize=8, framealpha=0.85, ncol=2)

    # --- Title & layout ---
    ax1.set_title(
        "7-Day & 14-Day Rolling Average — Gearbox Vibration & Motor Housing Temperature\n"
        "Degradation Trend Analysis | Manufacturing FYP Day 16",
        fontsize=13, fontweight="bold", pad=12,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[Plot 1] Saved -> {path}")
    return path


# ---------------------------------------------------------------------------
# PLOT 2 — Shift-Based OEE Seasonality Boxplot
# ---------------------------------------------------------------------------

def plot_shift_oee_seasonality(oee_df: pd.DataFrame) -> str:
    """
    Generate Plot 2: grouped boxplot of OEE, Availability, Performance, Quality
    stratified by shift label (DAY / SWING / NIGHT).

    Layout: 1 row × 4 columns (one box per OEE factor + composite OEE).
    Each column shows the distribution per shift label — allows visual
    comparison of whether any shift consistently underperforms.

    Returns path to saved PNG.
    """
    path = os.path.join(OUTPUT_DIR, "shift_oee_seasonality.png")

    metrics = [
        ("OEE_pct",  "OEE (%)"),
        ("A_pct",    "Availability (%)"),
        ("P_pct",    "Performance (%)"),
        ("Q_pct",    "Quality (%)"),
    ]

    sns.set_theme(style="darkgrid", font_scale=1.0)
    fig, axes = plt.subplots(1, 4, figsize=(18, 6), dpi=DPI, sharey=False)

    shift_order = ["DAY", "SWING", "NIGHT"]
    palette = [SHIFT_PALETTE[s] for s in shift_order]

    for ax, (col, label) in zip(axes, metrics):
        sns.boxplot(
            data=oee_df,
            x="shift_label",
            y=col,
            order=shift_order,
            hue="shift_label",
            hue_order=shift_order,
            palette=dict(zip(shift_order, palette)),
            legend=False,
            width=0.55,
            linewidth=1.4,
            flierprops={"marker": "o", "markersize": 3.5, "alpha": 0.5},
            ax=ax,
        )
        # Annotate medians
        medians = oee_df.groupby("shift_label")[col].median()
        for i, shift in enumerate(shift_order):
            if shift in medians:
                ax.text(
                    i, medians[shift] + 0.05,
                    f"{medians[shift]:.1f}",
                    ha="center", va="bottom", fontsize=8.5, fontweight="bold",
                    color="#111827",
                )
        ax.set_title(label, fontsize=11, fontweight="bold", pad=8)
        ax.set_xlabel("Shift", fontsize=9)
        ax.set_ylabel(label if ax == axes[0] else "", fontsize=9)
        ax.tick_params(axis="both", labelsize=9)

    fig.suptitle(
        "Shift-Based OEE Seasonality — Daily Cyclical Pattern Analysis\n"
        "Manufacturing FYP Day 16 | Shift Labels: DAY / SWING / NIGHT",
        fontsize=13, fontweight="bold", y=1.02,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    plt.rcdefaults()
    print(f"[Plot 2] Saved -> {path}")
    return path


# ---------------------------------------------------------------------------
# PLOT 3 — Stacked Daily Downtime vs Failure Log
# ---------------------------------------------------------------------------

def plot_downtime_vs_failures(daily_dt: pd.DataFrame,
                              failure_df: pd.DataFrame) -> str:
    """
    Generate Plot 3: stacked area chart of daily downtime (minutes) by category,
    overlaid with vertical event markers for each entry in failure_log.

    Layout:
        - Stacked area: dates on X, cumulative daily downtime minutes on Y.
        - Each category has its own fill colour from DOWNTIME_COLOURS.
        - Failure events: red dashed vertical lines with component name labels.
        - Legend identifies both downtime categories and failure event line.

    Returns path to saved PNG.
    """
    path = os.path.join(OUTPUT_DIR, "downtime_vs_failures_stacked.png")

    fig, ax = plt.subplots(figsize=(18, 6), dpi=DPI)

    # Only stack categories that actually have data
    cats_present = [c for c in DOWNTIME_COLOURS if c in daily_dt.columns]
    colours_ordered = [DOWNTIME_COLOURS[c] for c in cats_present]

    dates = daily_dt.index.to_pydatetime()
    values = [daily_dt[c].values for c in cats_present]

    ax.stackplot(
        dates,
        *values,
        labels=[c.replace("_", " ").title() for c in cats_present],
        colors=colours_ordered,
        alpha=0.82,
    )

    # --- Failure event markers ---
    failure_plotted_label = False
    for _, row in failure_df.iterrows():
        lbl = "Failure Event" if not failure_plotted_label else "_nolegend_"
        ax.axvline(
            row["failure_datetime"],
            color="#7C3AED", lw=1.2, ls="--", alpha=0.80,
            label=lbl,
            zorder=5,
        )
        failure_plotted_label = True
        # Component name annotation (rotated, tiny font)
        ax.text(
            row["failure_datetime"],
            ax.get_ylim()[1] * 0.92 if ax.get_ylim()[1] > 0 else 50,
            row["component_name"][:3],
            rotation=90, fontsize=6.5, color="#4C1D95",
            va="top", ha="right",
        )

    # --- Axes & formatting ---
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Daily Downtime (minutes)", fontsize=11)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(14))
    fig.autofmt_xdate(rotation=30, ha="right")

    ax.legend(
        loc="upper right", fontsize=8.5, framealpha=0.88,
        ncol=2, title="Category / Event", title_fontsize=9,
    )
    ax.set_title(
        "Daily Downtime (Stacked by Category) vs Failure Log Events\n"
        "Manufacturing FYP Day 16 | Downtime Cause Analysis",
        fontsize=13, fontweight="bold", pad=12,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[Plot 3] Saved -> {path}")
    return path


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Entry point: connect to DB, load data, generate all 3 plots, print summary.
    """
    print("=" * 65)
    print("eda_trends.py — Day 16: Trend & Seasonality Analysis")
    print("=" * 65)

    _ensure_output_dir()

    conn = _connect()

    try:
        # ---- Load data ----
        print("\n[1/3] Loading sensor time-series data …")
        sensor_df = load_sensor_timeseries(conn)
        print(f"      Sensor rows: {len(sensor_df)} daily data-points "
              f"({sensor_df.index.min().date()} -> {sensor_df.index.max().date()})")

        print("[2/3] Computing shift-level OEE …")
        oee_df = load_shift_oee(conn)
        print(f"      OEE rows: {len(oee_df)} shifts | "
              f"Shift labels: {sorted(oee_df['shift_label'].unique())}")

        print("[3/3] Loading downtime + failure log …")
        daily_dt, failure_df = load_downtime_and_failures(conn)
        print(f"      Downtime days: {len(daily_dt)} | "
              f"Failure events: {len(failure_df)}")

        # ---- Generate plots ----
        print("\n--- Generating plots ---")
        p1 = plot_rolling_sensor_trends(sensor_df)
        p2 = plot_shift_oee_seasonality(oee_df)
        p3 = plot_downtime_vs_failures(daily_dt, failure_df)

        # ---- Summary ----
        print("\n" + "=" * 65)
        print("All 3 plots saved successfully:")
        for i, p in enumerate((p1, p2, p3), 1):
            print(f"  Plot {i}: {p}")

        print("\nKey metrics:")
        print(f"  Gearbox vib — 7-day rolling max:  "
              f"{sensor_df['gearbox_vib'].rolling(7, min_periods=1).mean().max():.3f} mm/s")
        print(f"  Motor temp  — 14-day rolling max: "
              f"{sensor_df['motor_temp'].rolling(14, min_periods=1).mean().max():.2f} °C")

        med_oee = oee_df.groupby("shift_label")["OEE_pct"].median().round(2)
        print(f"  Median OEE by shift:\n    {med_oee.to_dict()}")

        tot_downtime = daily_dt.sum().sum()
        print(f"  Total downtime across all days:   {tot_downtime:,.0f} min "
              f"(approx. {tot_downtime / 60:.1f} hrs)")
        print("=" * 65)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
