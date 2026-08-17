"""
composite_criticality.py  --  Day 19 Deliverable
Manufacturing and Industrial Analytics FYP
Date: August 2, 2026

PURPOSE
-------
Calculate a single Composite Criticality Index (CCI) for all 5 pipeline
components by normalising and weighting three existing risk metrics:

  Metric 1 -- Structural Risk Score (SRS)
      Source: data/processed/graph_centrality_rankings.csv  (Day 18)
      Captures: graph-theoretic bottleneck severity (betweenness centrality,
                cascade reach, cascade exposure).

  Metric 2 -- Weibull Reliability  R(t)  at current operating age
      Source: Component-level Weibull parameters (eta, beta_mid) locked in
              sql/seed.sql (Day 4) and validated in tests/test_reliability.py.
              Operating age t_hours = 2920 h (mid-life evaluation point).
      R(t) = exp( -(t / eta)^beta )
      NOTE: High R(t) => component is reliable => LOW criticality.
            The metric is INVERTED before weighting:  unreliability = 1 - R(t).

  Metric 3 -- Threshold Breach Rate (TBR)
      Source: data/processed/multi_failure_telemetry.csv
      ISO/IEC alarm limits locked in docs/EDA_FINDINGS.md (Day 17):
        Vibration alarm  : > 4.5  mm/s   (ISO 10816-3 Zone C)
        Temperature alarm: > 80   deg C  (Bearing), 130 deg C (Motor Housing),
                                          90 deg C  (Gearbox)
        Oil debris alarm : > 50   counts/mL (ISO 4406)
        Load alarm       : > 90   pct     (Coupling design limit)
        RPM              : no universal alarm -- excluded from TBR
      TBR(c) = (rows where value > alarm_limit) / (total eligible rows)

COMPOSITE CRITICALITY INDEX (CCI)
----------------------------------
CCI(c) = 0.40 * SRS_norm(c) + 0.35 * Unreliability_norm(c) + 0.25 * TBR_norm(c)

Weights (locked Day 19):
  w1 = 0.40   (structural / topological risk -- graph bottleneck severity)
  w2 = 0.35   (reliability degradation -- Weibull wear-out)
  w3 = 0.25   (operational breach frequency -- real sensor data evidence)

All three sub-metrics are normalised to [0, 1] by dividing by their
respective maximum across the 5 components before weighting.

OUTPUTS
-------
  Console ranking table
  data/processed/criticality_scores.csv
  data/processed/plots/criticality_index_plot.png

REFERENCES
----------
  Day 4  : Weibull parameters (eta, beta) locked in sql/seed.sql
  Day 11 : multi_failure_telemetry.csv -- simulation dataset (47,998 rows)
  Day 17 : ISO/IEC alarm limits locked in docs/EDA_FINDINGS.md Section 5
  Day 18 : SRS values locked in data/processed/graph_centrality_rankings.csv
"""

import os
import math
import sqlite3

import numpy as np
import pandas as pd
import scipy.special
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ===========================================================================
# SECTION 1 -- LOCKED PARAMETERS
# ===========================================================================

PIPELINE_ORDER = ["Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"]

def get_db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "manufacturing.db")

def load_weibull_params():
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    cur.execute("SELECT component_name, weibull_beta_mid, weibull_eta_hours FROM components")
    params = {row[0]: {"beta": row[1], "eta": row[2]} for row in cur.fetchall()}
    conn.close()
    return params

def load_alarm_limits():
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    cur.execute('''
        SELECT c.component_name, s.sensor_type, s.iso_alarm_threshold
        FROM sensors s
        JOIN components c ON s.component_id = c.component_id
        WHERE s.iso_alarm_threshold IS NOT NULL
    ''')
    limits = {}
    for row in cur.fetchall():
        limits.setdefault(row[0], {})[row[1]] = row[2]
    conn.close()
    return limits

# Parameters loaded dynamically from database
WEIBULL_PARAMS = load_weibull_params()
ALARM_LIMITS = load_alarm_limits()

# SRS fallback (from graph_centrality_rankings.csv Day 18)
SRS_FALLBACK = {
    "Motor Housing": 0.7500,
    "Shaft":         0.6500,
    "Coupling":      0.6000,
    "Bearing":       0.3000,
    "Gearbox":       0.2000,
}

# Weight vector -- LOCKED Day 19
W_SRS           = 0.40
W_UNRELIABILITY = 0.35
W_TBR           = 0.25

# Operating age for R(t) evaluation (mid-life, consistent with MTBF analysis)
T_OPERATING_HOURS = 2920.0

# ===========================================================================
# SECTION 2 -- FILE PATHS
# ===========================================================================

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
PLOTS_DIR     = os.path.join(PROCESSED_DIR, "plots")
TELEMETRY_CSV = os.path.join(PROCESSED_DIR, "multi_failure_telemetry.csv")
SRS_CSV       = os.path.join(PROCESSED_DIR, "graph_centrality_rankings.csv")
OUTPUT_CSV    = os.path.join(PROCESSED_DIR, "criticality_scores.csv")
OUTPUT_PLOT   = os.path.join(PLOTS_DIR, "criticality_index_plot.png")

os.makedirs(PLOTS_DIR, exist_ok=True)

# ===========================================================================
# SECTION 3 -- METRIC COMPUTATION FUNCTIONS
# ===========================================================================

def weibull_reliability(t, beta, eta):
    """R(t) = exp(-(t/eta)^beta). Raises ValueError for invalid inputs."""
    if t < 0:
        raise ValueError("Operating age t must be >= 0.")
    if beta <= 0:
        raise ValueError("Weibull shape beta must be > 0.")
    if eta <= 0:
        raise ValueError("Weibull scale eta must be > 0.")
    if t == 0:
        return 1.0
    return math.exp(-((t / eta) ** beta))


def load_srs_scores(srs_csv_path):
    """Load SRS from Day 18 CSV. Falls back to hardcoded constants if missing."""
    if not os.path.isfile(srs_csv_path):
        print("[WARN] graph_centrality_rankings.csv not found -- using hardcoded SRS fallback.")
        return dict(SRS_FALLBACK)
    df = pd.read_csv(srs_csv_path)
    srs_dict = {str(row["component"]).strip(): float(row["structural_risk_score"])
                for _, row in df.iterrows()}
    print("[INFO] SRS scores loaded from: {}".format(srs_csv_path))
    return srs_dict


def compute_weibull_unreliabilities(t_hours):
    """Compute 1 - R(t) for all 5 components at t_hours."""
    results = {}
    print("\n[INFO] Weibull R(t) at t = {:.0f} h:".format(t_hours))
    print("  {:<18}  {:>6}  {:>8}  {:>10}  {:>12}".format(
        "Component", "beta", "eta(h)", "R(t)", "1-R(t)"))
    print("  " + "-" * 60)
    for comp in PIPELINE_ORDER:
        p = WEIBULL_PARAMS[comp]
        rt = weibull_reliability(t_hours, p["beta"], p["eta"])
        ut = 1.0 - rt
        results[comp] = ut
        print("  {:<18}  {:>6.2f}  {:>8.0f}  {:>10.6f}  {:>12.6f}".format(
            comp, p["beta"], p["eta"], rt, ut))
    return results


def compute_threshold_breach_rates(telemetry_csv):
    """
    Compute TBR(c) = breaching readings / eligible readings per component.
    Only sensor types with a defined alarm limit are counted.
    """
    print("\n[INFO] Loading telemetry: {}".format(telemetry_csv))
    df = pd.read_csv(
        telemetry_csv,
        usecols=["component_name", "sensor_type", "value"],
        dtype={"component_name": str, "sensor_type": str, "value": float},
    )
    print("  Rows loaded: {:,}".format(len(df)))

    tbr_results = {}
    print("\n[INFO] Threshold Breach Rates (TBR):")
    print("  {:<18}  {:>10}  {:>10}  {:>10}".format(
        "Component", "Eligible", "Breaches", "TBR"))
    print("  " + "-" * 52)

    for comp in PIPELINE_ORDER:
        comp_df = df[df["component_name"] == comp].copy()
        alarm_dict = ALARM_LIMITS.get(comp, {})

        eligible_df = comp_df[comp_df["sensor_type"].isin(alarm_dict.keys())].copy()
        total_eligible = len(eligible_df)

        if total_eligible == 0:
            tbr_results[comp] = 0.0
            print("  {:<18}  {:>10}  {:>10}  {:>10.6f}".format(comp, 0, 0, 0.0))
            continue

        def is_breach(row):
            limit = alarm_dict.get(row["sensor_type"])
            return (limit is not None) and (row["value"] > limit)

        n_breaches = int(eligible_df.apply(is_breach, axis=1).sum())
        tbr = n_breaches / total_eligible
        tbr_results[comp] = tbr
        print("  {:<18}  {:>10,}  {:>10,}  {:>10.6f}".format(
            comp, total_eligible, n_breaches, tbr))

    return tbr_results


def max_normalise(values, invert=False):
    """
    Normalise dict values to [0,1] by dividing by the maximum.
    Consistent with SRS normalisation in graph_centrality.py (Day 18).
    """
    max_val = max(values.values()) if values else 0.0
    if max_val == 0.0:
        return {k: 0.0 for k in values}
    if invert:
        return {k: 1.0 - (v / max_val) for k, v in values.items()}
    return {k: v / max_val for k, v in values.items()}


def compute_composite_criticality(srs, unreliability, tbr,
                                  w_srs=W_SRS, w_unrel=W_UNRELIABILITY, w_tbr=W_TBR):
    """
    CCI(c) = w_srs * SRS_norm(c) + w_unrel * Unreliability_norm(c) + w_tbr * TBR_norm(c)
    Weights must sum to 1.0.
    """
    if abs(w_srs + w_unrel + w_tbr - 1.0) > 1e-9:
        raise ValueError("Weights must sum to 1.0, got {:.6f}".format(w_srs + w_unrel + w_tbr))

    srs_norm   = max_normalise(srs,           invert=False)
    unrel_norm = max_normalise(unreliability, invert=False)
    tbr_norm   = max_normalise(tbr,           invert=False)

    rows = []
    for comp in PIPELINE_ORDER:
        sn = srs_norm.get(comp, 0.0)
        un = unrel_norm.get(comp, 0.0)
        tn = tbr_norm.get(comp, 0.0)
        cci = w_srs * sn + w_unrel * un + w_tbr * tn
        
        # Calculate theoretical Weibull MTBF = eta * Gamma(1 + 1/beta)
        p = WEIBULL_PARAMS.get(comp, {"beta": 1.0, "eta": 1.0})
        weibull_mtbf_hours = p["eta"] * scipy.special.gamma(1 + 1/p["beta"])

        rows.append({
            "component":             comp,
            "structural_risk_score": srs.get(comp, 0.0),
            "weibull_unreliability": unreliability.get(comp, 0.0),
            "threshold_breach_rate": tbr.get(comp, 0.0),
            "srs_norm":              round(sn,  6),
            "unreliability_norm":    round(un,  6),
            "tbr_norm":              round(tn,  6),
            "cci_srs_contrib":       round(w_srs   * sn, 6),
            "cci_unrel_contrib":     round(w_unrel * un, 6),
            "cci_tbr_contrib":       round(w_tbr   * tn, 6),
            "composite_criticality": round(cci, 6),
            "w_srs":                 w_srs,
            "w_unreliability":       w_unrel,
            "w_tbr":                 w_tbr,
            "t_eval_hours":          T_OPERATING_HOURS,
            "weibull_mtbf_hours":    round(weibull_mtbf_hours, 6)
        })

    df_out = (pd.DataFrame(rows)
              .sort_values("composite_criticality", ascending=False)
              .reset_index(drop=True))
    df_out.insert(0, "cci_rank", range(1, len(df_out) + 1))
    return df_out


# ===========================================================================
# SECTION 4 -- VISUALISATION
# ===========================================================================

DARK_BG  = "#0D1117"
PANEL_BG = "#161B22"
GRID_COL = "#30363D"
TEXT_COL = "#C9D1D9"
MUTED    = "#8B949E"


def plot_criticality_index(df, output_path):
    """
    Stacked horizontal bar chart: CCI broken down by weighted sub-metric
    contributions (SRS / Unreliability / TBR) for all 5 components.
    Dark theme, DPI=150.
    """
    df_plot = df.sort_values("composite_criticality", ascending=True).copy()
    components = df_plot["component"].tolist()
    srs_c   = df_plot["cci_srs_contrib"].values
    unrel_c = df_plot["cci_unrel_contrib"].values
    tbr_c   = df_plot["cci_tbr_contrib"].values
    cci_val = df_plot["composite_criticality"].values
    ranks   = df_plot["cci_rank"].values

    fig, ax = plt.subplots(figsize=(13, 7))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(PANEL_BG)

    y_pos = np.arange(len(components))
    bar_h = 0.55

    ax.barh(y_pos, srs_c, height=bar_h, color="#58A6FF", alpha=0.92,
            label="SRS contribution  (w=0.40)", edgecolor="none")
    ax.barh(y_pos, unrel_c, height=bar_h, left=srs_c, color="#FF8C42", alpha=0.92,
            label="Unreliability 1-R(t) contribution  (w=0.35)", edgecolor="none")
    ax.barh(y_pos, tbr_c, height=bar_h, left=srs_c + unrel_c, color="#FF5580", alpha=0.92,
            label="TBR contribution  (w=0.25)", edgecolor="none")

    for i, (comp, cci, rank) in enumerate(zip(components, cci_val, ranks)):
        ax.text(cci + 0.008, i,
                "  CCI={:.4f}  [Rank {}]".format(cci, int(rank)),
                va="center", ha="left", fontsize=9.5,
                color=TEXT_COL, fontfamily="monospace")

    ax.axvline(x=0.5, color=MUTED, linestyle="--", linewidth=1.1, alpha=0.7,
               label="CCI = 0.50 (moderate/high boundary)")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(components, fontsize=11, color=TEXT_COL)
    ax.set_xlim(0, 1.10)
    ax.set_xlabel("Composite Criticality Index (CCI)", fontsize=11,
                  color=TEXT_COL, labelpad=8)
    ax.tick_params(axis="x", colors=MUTED, labelsize=9)
    ax.tick_params(axis="y", colors=MUTED)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(GRID_COL)
    ax.spines["bottom"].set_color(GRID_COL)
    ax.xaxis.grid(True, color=GRID_COL, linewidth=0.6, alpha=0.5)
    ax.set_axisbelow(True)

    fig.suptitle("Composite Criticality Index (CCI)  --  Day 19",
                 fontsize=15, fontweight="bold", color=TEXT_COL, y=0.97)
    ax.set_title(
        "CCI = 0.40*SRS  +  0.35*(1-R(t))  +  0.25*TBR   |   t = {:.0f} h".format(
            T_OPERATING_HOURS),
        fontsize=9.5, color=MUTED, pad=8)

    ax.legend(loc="lower right", fontsize=8.5,
              facecolor=PANEL_BG, edgecolor=GRID_COL,
              labelcolor=TEXT_COL, framealpha=0.9)

    formula_text = (
        "CCI = w1*SRS_norm + w2*(1-R(t))_norm + w3*TBR_norm\n"
        "w1=0.40  w2=0.35  w3=0.25   (sum=1.00)\n"
        "R(t) = exp(-(t/eta)^beta)   t={:.0f} h".format(T_OPERATING_HOURS)
    )
    ax.text(0.99, 0.02, formula_text, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7.5, color=MUTED,
            fontfamily="monospace",
            bbox=dict(facecolor=DARK_BG, edgecolor=GRID_COL, alpha=0.85, pad=4))

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    plt.close()
    print("\n[INFO] Plot saved: {}".format(output_path))


# ===========================================================================
# SECTION 5 -- CONSOLE REPORTING
# ===========================================================================

def print_results_table(df):
    """Print a formatted console summary of the CCI ranking."""
    print("\n" + "=" * 76)
    print("  COMPOSITE CRITICALITY INDEX RANKING  --  Day 19")
    print("  CCI = 0.40*SRS_norm + 0.35*Unreliability_norm + 0.25*TBR_norm")
    print("  t = {:.0f} h | Weibull beta_mid, eta from seed.sql (Day 4)".format(
        T_OPERATING_HOURS))
    print("=" * 76)
    print("  {:>4}  {:<18}  {:>6}  {:>10}  {:>7}  {:>8}".format(
        "Rank", "Component", "SRS", "1-R(t)", "TBR", "CCI"))
    print("  " + "-" * 62)
    for _, row in df.iterrows():
        print("  {:>4}  {:<18}  {:>6.4f}  {:>10.6f}  {:>7.4f}  {:>8.6f}".format(
            int(row["cci_rank"]), row["component"],
            row["structural_risk_score"],
            row["weibull_unreliability"],
            row["threshold_breach_rate"],
            row["composite_criticality"]))
    print("=" * 76)
    top = df.iloc[0]
    bot = df.iloc[-1]
    print("  MOST CRITICAL : {} (CCI = {:.4f})".format(
        top["component"], top["composite_criticality"]))
    print("  LEAST CRITICAL: {} (CCI = {:.4f})".format(
        bot["component"], bot["composite_criticality"]))
    print("=" * 76)
    print("\n  Contribution breakdown:")
    print("  {:>4}  {:<18}  {:>10}  {:>12}  {:>10}".format(
        "Rank", "Component", "SRS_c", "Unrel_c", "TBR_c"))
    print("  " + "-" * 60)
    for _, row in df.iterrows():
        print("  {:>4}  {:<18}  {:>10.4f}  {:>12.4f}  {:>10.4f}".format(
            int(row["cci_rank"]), row["component"],
            row["cci_srs_contrib"], row["cci_unrel_contrib"], row["cci_tbr_contrib"]))
    print("=" * 76)


# ===========================================================================
# SECTION 6 -- MAIN ENTRY POINT
# ===========================================================================

def main():
    print("=" * 76)
    print("  composite_criticality.py  --  Day 19")
    print("  Manufacturing and Industrial Analytics FYP")
    print("=" * 76)

    srs_dict           = load_srs_scores(SRS_CSV)
    unreliability_dict = compute_weibull_unreliabilities(T_OPERATING_HOURS)
    tbr_dict           = compute_threshold_breach_rates(TELEMETRY_CSV)

    print("\n[INFO] Computing CCI ...")
    print("  Weights: SRS={:.2f}, Unreliability={:.2f}, TBR={:.2f}".format(
        W_SRS, W_UNRELIABILITY, W_TBR))

    df_cci = compute_composite_criticality(
        srs=srs_dict, unreliability=unreliability_dict, tbr=tbr_dict)

    print_results_table(df_cci)

    df_cci.to_csv(OUTPUT_CSV, index=False)
    print("\n[INFO] CSV saved: {}".format(OUTPUT_CSV))

    plot_criticality_index(df_cci, OUTPUT_PLOT)

    print("\n[DONE] Day 19 complete.")
    print("  CSV : {}".format(OUTPUT_CSV))
    print("  Plot: {}".format(OUTPUT_PLOT))
    print("=" * 76)
    return df_cci


if __name__ == "__main__":
    main()
