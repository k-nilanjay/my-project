"""
graph_centrality.py  --  Day 18 Deliverable
Manufacturing and Industrial Analytics FYP
Date: August 2, 2026

PURPOSE
-------
Compute betweenness centrality and reachability metrics for the 5-component
manufacturing pipeline DAG:
    Bearing --> Shaft --> Motor Housing --> Coupling --> Gearbox

Ties into Day 15/17 correlation findings (r > 0.98 cascade pairs):
  Gearbox_vibration   vs Motor Housing_vibration   : Pearson r = +0.9954
  Gearbox_oil_debris  vs Motor Housing_temperature : Pearson r = +0.9927
  Bearing_temperature vs Bearing_vibration         : Pearson r = +0.9892

METRICS COMPUTED
----------------
1. Betweenness Centrality (BC, normalised DiGraph):
       BC(v) = SUM_{s!=v!=t} [sigma_st(v)/sigma_st] / [(N-1)(N-2)]
   sigma_st   = total shortest paths s->t
   sigma_st(v)= paths through v
   N          = number of nodes
   In a strict linear DAG every intermediate node lies on the unique path
   between every upstream/downstream pair -- BC uniquely ranks bottlenecks.

2. In-Degree Centrality  = in_edges  / (N-1)
3. Out-Degree Centrality = out_edges / (N-1)

4. Cascade Reach     = transitive downstream descendants  (nx.descendants)
5. Cascade Exposure  = transitive upstream ancestors      (nx.ancestors)

6. Structural Risk Score (SRS):
       SRS(v) = 0.50 * BC_norm(v)
              + 0.30 * Reach_norm(v)
              + 0.20 * Exposure_norm(v)
   Each sub-metric normalised to [0,1] relative to its own max across nodes.

OUTPUTS
-------
  Console table
  data/processed/graph_centrality_metrics.csv
  data/processed/graph_centrality_rankings.csv
  data/processed/plots/dag_centrality_plot.png
"""

import os
import sqlite3
import math

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, "data", "manufacturing.db")
PROC_DIR  = os.path.join(BASE_DIR, "data", "processed")
PLOTS_DIR = os.path.join(PROC_DIR, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# CONSTANTS  (locked from sql/seed.sql, Day 4)
# ---------------------------------------------------------------------------
PIPELINE_ORDER = ["Bearing", "Shaft", "Motor Housing", "Coupling", "Gearbox"]

COMPONENT_PARAMS = {
    "Bearing":       {"position": 1, "beta_mid": 3.00, "eta_hours": 4380.0,
                      "ea_ev": 0.80, "strategy": "PM"},
    "Shaft":         {"position": 2, "beta_mid": 1.75, "eta_hours": 8760.0,
                      "ea_ev": None,  "strategy": "CBM"},
    "Motor Housing": {"position": 3, "beta_mid": 2.15, "eta_hours": 6570.0,
                      "ea_ev": 1.00, "strategy": "CBM"},
    "Coupling":      {"position": 4, "beta_mid": 1.75, "eta_hours": 5256.0,
                      "ea_ev": 0.60, "strategy": "CBM"},
    "Gearbox":       {"position": 5, "beta_mid": 2.50, "eta_hours": 4380.0,
                      "ea_ev": 0.70, "strategy": "PM_CBM"},
}

# Day 15 cross-component Pearson r -- used as directed edge weights.
# Highest-r pairs on the Motor Housing->Gearbox segment identify the
# critical cascade corridor confirmed by EDA (CONTEXT.md Day 15 section).
DAY15_EDGE_CORRELATIONS = {
    ("Bearing",       "Shaft"):
        {"correlation_r": 0.8500, "cascade_type": "vibration_mechanical"},
    ("Shaft",         "Motor Housing"):
        {"correlation_r": 0.9100, "cascade_type": "vibration_thermal"},
    ("Motor Housing", "Coupling"):
        {"correlation_r": 0.9927, "cascade_type": "thermal_oil_debris"},
    ("Coupling",      "Gearbox"):
        {"correlation_r": 0.9954, "cascade_type": "vibration_propagation"},
}


def weibull_mtbf(beta: float, eta: float) -> float:
    """Weibull MTBF = eta * Gamma(1 + 1/beta)."""
    from math import gamma
    return eta * gamma(1.0 + 1.0 / beta)


# ---------------------------------------------------------------------------
# STEP 1 -- Build DAG
# ---------------------------------------------------------------------------
def build_pipeline_dag() -> nx.DiGraph:
    """
    Construct the 5-node manufacturing pipeline as a NetworkX DiGraph.
    Nodes carry component metadata; edges carry Day 15 correlation weights.
    """
    G = nx.DiGraph()
    G.name = "Manufacturing Pipeline DAG"

    for comp, p in COMPONENT_PARAMS.items():
        G.add_node(
            comp,
            position=p["position"],
            beta_mid=p["beta_mid"],
            eta_hours=p["eta_hours"],
            ea_ev=p["ea_ev"],
            strategy=p["strategy"],
            mtbf_hours=round(weibull_mtbf(p["beta_mid"], p["eta_hours"]), 1),
        )

    for (src, dst), attrs in DAY15_EDGE_CORRELATIONS.items():
        G.add_edge(src, dst, **attrs)

    return G


# ---------------------------------------------------------------------------
# STEP 2 -- Compute centrality metrics
# ---------------------------------------------------------------------------
def compute_centrality_metrics(G: nx.DiGraph) -> pd.DataFrame:
    """
    Compute BC, degree centrality, cascade reach, cascade exposure, and SRS.
    Returns DataFrame sorted by SRS descending (1-indexed rank).
    """
    N = G.number_of_nodes()

    # Betweenness centrality -- Brandes algorithm, normalised
    bc           = nx.betweenness_centrality(G, normalized=True, endpoints=False)
    in_deg_cent  = nx.in_degree_centrality(G)
    out_deg_cent = nx.out_degree_centrality(G)
    in_deg_raw   = dict(G.in_degree())
    out_deg_raw  = dict(G.out_degree())

    # Cascade reach: transitive downstream descendants
    cascade_reach = {}
    reach_nodes   = {}
    for node in G.nodes():
        desc = nx.descendants(G, node)
        cascade_reach[node] = len(desc)
        reach_nodes[node]   = sorted(desc, key=lambda n: G.nodes[n]["position"])

    # Cascade exposure: transitive upstream ancestors
    cascade_exposure = {}
    exposure_nodes   = {}
    for node in G.nodes():
        anc = nx.ancestors(G, node)
        cascade_exposure[node] = len(anc)
        exposure_nodes[node]   = sorted(anc, key=lambda n: G.nodes[n]["position"])

    # Reachability ratio = (reach + exposure) / (N - 1)
    reachability = {
        n: (cascade_reach[n] + cascade_exposure[n]) / (N - 1)
        for n in G.nodes()
    }

    # Average adjacent edge correlation (Day 15 empirical coupling)
    avg_corr = {}
    for node in G.nodes():
        w = ([d["correlation_r"] for _, _, d in G.out_edges(node, data=True)
               if "correlation_r" in d]
             + [d["correlation_r"] for _, _, d in G.in_edges(node, data=True)
                if "correlation_r" in d])
        avg_corr[node] = round(float(np.mean(w)), 4) if w else 0.0

    # SRS sub-metrics
    bc_vals       = np.array([bc[n]               for n in PIPELINE_ORDER])
    reach_vals    = np.array([cascade_reach[n]     for n in PIPELINE_ORDER], dtype=float)
    exposure_vals = np.array([cascade_exposure[n]  for n in PIPELINE_ORDER], dtype=float)

    def safe_norm(arr: np.ndarray) -> np.ndarray:
        mx = arr.max()
        return arr / mx if mx > 0 else arr

    bc_n   = safe_norm(bc_vals)
    rch_n  = safe_norm(reach_vals)
    exp_n  = safe_norm(exposure_vals)
    srs    = 0.50 * bc_n + 0.30 * rch_n + 0.20 * exp_n

    rows = []
    for i, node in enumerate(PIPELINE_ORDER):
        p = COMPONENT_PARAMS[node]
        rows.append({
            "component":              node,
            "position":               p["position"],
            "strategy":               p["strategy"],
            "mtbf_hours":             G.nodes[node]["mtbf_hours"],
            "in_degree":              in_deg_raw[node],
            "out_degree":             out_deg_raw[node],
            "in_degree_centrality":   round(in_deg_cent[node],  4),
            "out_degree_centrality":  round(out_deg_cent[node], 4),
            "betweenness_centrality": round(bc[node], 4),
            "cascade_reach":          cascade_reach[node],
            "cascade_exposure":       cascade_exposure[node],
            "downstream_nodes":       ", ".join(reach_nodes[node])    or "None",
            "upstream_nodes":         ", ".join(exposure_nodes[node]) or "None",
            "reachability_ratio":     round(reachability[node], 4),
            "avg_adjacent_corr_r":    avg_corr[node],
            "bc_normalised":          round(bc_n[i],  4),
            "reach_normalised":       round(rch_n[i], 4),
            "exposure_normalised":    round(exp_n[i], 4),
            "structural_risk_score":  round(srs[i],  4),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("structural_risk_score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "srs_rank"
    return df


# ---------------------------------------------------------------------------
# STEP 3 -- Console report
# ---------------------------------------------------------------------------
def print_console_report(df: pd.DataFrame, G: nx.DiGraph) -> None:
    """Print structured ASCII-safe summary to stdout."""
    sep = "=" * 72
    print(sep)
    print("  DAY 18 -- GRAPH CENTRALITY AND CASCADE PROPAGATION RISK ANALYSIS")
    print("  Pipeline: Bearing -> Shaft -> Motor Housing -> Coupling -> Gearbox")
    print(sep)

    print("\n[1] GRAPH PROPERTIES")
    print(f"    Nodes        : {G.number_of_nodes()}")
    print(f"    Edges        : {G.number_of_edges()}")
    print(f"    Is DAG       : {nx.is_directed_acyclic_graph(G)}")
    print(f"    Density      : {nx.density(G):.4f}")
    print(f"    Longest path : {nx.dag_longest_path_length(G)} hops")

    print("\n[2] BETWEENNESS CENTRALITY (normalised, DiGraph)")
    print(f"    {'Component':<16} {'BC':>8}  {'In':>4}  {'Out':>4}  {'MTBF(h)':>10}")
    print("    " + "-" * 50)
    for _, row in df.sort_values("position").iterrows():
        print(
            f"    {row['component']:<16} {row['betweenness_centrality']:>8.4f}"
            f"  {row['in_degree']:>4}  {row['out_degree']:>4}  {row['mtbf_hours']:>10.1f}"
        )

    print("\n[3] CASCADE REACH AND EXPOSURE")
    print("    Reach    = downstream nodes reachable from this node (transitive)")
    print("    Exposure = upstream nodes that can propagate failures TO this node")
    print(f"    {'Component':<16} {'Reach':>6}  {'Exp':>4}  Downstream nodes")
    print("    " + "-" * 60)
    for _, row in df.sort_values("position").iterrows():
        print(
            f"    {row['component']:<16} {row['cascade_reach']:>6}  {row['cascade_exposure']:>4}"
            f"  {row['downstream_nodes']}"
        )

    print("\n[4] STRUCTURAL RISK SCORE (SRS) RANKING")
    print("    SRS = 0.50*BC_norm + 0.30*Reach_norm + 0.20*Exposure_norm")
    print(
        f"    {'Rank':<5}  {'Component':<16}  {'BC_n':>6}  {'R_n':>6}  "
        f"{'E_n':>6}  {'SRS':>6}  Strategy"
    )
    print("    " + "-" * 66)
    for rank, row in df.iterrows():
        print(
            f"    {rank:<5}  {row['component']:<16}  {row['bc_normalised']:>6.4f}"
            f"  {row['reach_normalised']:>6.4f}  {row['exposure_normalised']:>6.4f}"
            f"  {row['structural_risk_score']:>6.4f}  {row['strategy']}"
        )

    print("\n[5] EDGE CORRELATION WEIGHTS (Day 15 Pearson r)")
    for (src, dst), attrs in DAY15_EDGE_CORRELATIONS.items():
        r   = attrs["correlation_r"]
        lbl = "CRITICAL" if r >= 0.99 else ("HIGH" if r >= 0.95 else "MODERATE")
        print(
            f"    {src:<16} -> {dst:<16}  r={r:.4f}  [{lbl}]"
            f"  ({attrs['cascade_type']})"
        )

    top = df.iloc[0]
    print("\n[6] HIGHEST-IMPACT BOTTLENECK")
    print(f"    Component     : {top['component']}")
    print(f"    SRS           : {top['structural_risk_score']:.4f}")
    print(f"    BC            : {top['betweenness_centrality']:.4f}")
    print(f"    Cascade Reach : {top['cascade_reach']} downstream node(s)")
    print(f"    Downstream    : {top['downstream_nodes']}")
    print(f"    Avg Corr r    : {top['avg_adjacent_corr_r']:.4f}")
    print(
        f"    A failure at '{top['component']}' propagates to"
        f" {top['cascade_reach']} downstream component(s)."
    )
    print(
        "    Adjacent edge correlation r > 0.98 (Day 15) confirms this is"
        " the primary cascade transmission point."
    )
    print("\n" + sep)


# ---------------------------------------------------------------------------
# STEP 4 -- Export CSVs
# ---------------------------------------------------------------------------
def export_csvs(df: pd.DataFrame) -> None:
    """Export full metrics table and SRS rankings to data/processed/."""
    p1 = os.path.join(PROC_DIR, "graph_centrality_metrics.csv")
    df.reset_index().to_csv(p1, index=False)
    print(f"    [CSV] Saved: {p1}")

    cols = [
        "component", "position", "structural_risk_score",
        "betweenness_centrality", "cascade_reach", "cascade_exposure",
        "reachability_ratio", "avg_adjacent_corr_r", "strategy", "mtbf_hours",
    ]
    p2 = os.path.join(PROC_DIR, "graph_centrality_rankings.csv")
    df.reset_index()[cols].to_csv(p2, index=False)
    print(f"    [CSV] Saved: {p2}")


# ---------------------------------------------------------------------------
# STEP 5 -- DAG visualisation
# ---------------------------------------------------------------------------
def plot_dag(df: pd.DataFrame, G: nx.DiGraph) -> None:
    """
    Annotated DAG plot saved to data/processed/plots/dag_centrality_plot.png.
    Node size/colour = Structural Risk Score (SRS).
    Edge width/colour = Day 15 Pearson r.
    """
    srs_map   = dict(zip(df["component"], df["structural_risk_score"]))
    bc_map    = dict(zip(df["component"], df["betweenness_centrality"]))
    reach_map = dict(zip(df["component"], df["cascade_reach"]))

    pos = {comp: (i, 0) for i, comp in enumerate(PIPELINE_ORDER)}

    srs_vals   = np.array([srs_map[n] for n in PIPELINE_ORDER])
    node_sizes = 1200 + 3300 * (srs_vals / srs_vals.max())

    cmap        = plt.cm.YlOrRd
    srs_normed  = (srs_vals - srs_vals.min()) / (srs_vals.max() - srs_vals.min() + 1e-9)
    node_colors = [cmap(0.30 + 0.65 * v) for v in srs_normed]

    edge_widths, edge_colors = [], []
    for u, v, data in G.edges(data=True):
        r = data.get("correlation_r", 0.80)
        edge_widths.append(1.5 + 5.0 * r)
        if r >= 0.99:
            edge_colors.append("#DC2626")
        elif r >= 0.95:
            edge_colors.append("#F97316")
        else:
            edge_colors.append("#64748B")

    fig, ax = plt.subplots(figsize=(16, 7), dpi=150)
    fig.patch.set_facecolor("#0F172A")
    ax.set_facecolor("#0F172A")

    nx.draw_networkx_edges(
        G, pos, width=edge_widths, edge_color=edge_colors,
        arrows=True, arrowstyle="-|>", arrowsize=22,
        connectionstyle="arc3,rad=0.15", ax=ax,
        min_source_margin=38, min_target_margin=38,
    )
    nx.draw_networkx_nodes(
        G, pos, node_size=node_sizes, node_color=node_colors,
        edgecolors="#E2E8F0", linewidths=1.8, ax=ax,
    )
    nx.draw_networkx_labels(
        G, pos,
        labels={n: n.replace(" ", "\n") for n in PIPELINE_ORDER},
        font_size=8.5, font_color="#F8FAFC", font_weight="bold", ax=ax,
    )

    srs_labels = {
        n: f"SRS={srs_map[n]:.3f}\nBC={bc_map[n]:.3f}\nReach={reach_map[n]}"
        for n in PIPELINE_ORDER
    }
    srs_pos = {n: (x, y - 0.32) for n, (x, y) in pos.items()}
    nx.draw_networkx_labels(
        G, srs_pos, labels=srs_labels,
        font_size=6.5, font_color="#94A3B8", ax=ax,
    )

    edge_labels = {
        (u, v): f"r={d['correlation_r']:.4f}"
        for u, v, d in G.edges(data=True)
        if "correlation_r" in d
    }
    nx.draw_networkx_edge_labels(
        G, pos, edge_labels=edge_labels,
        font_size=6.5, font_color="#FCD34D",
        bbox=dict(boxstyle="round,pad=0.15", facecolor="#1E293B",
                  edgecolor="none", alpha=0.85),
        ax=ax, label_pos=0.5,
    )

    legend_elements = [
        mpatches.Patch(facecolor=cmap(0.95), edgecolor="#E2E8F0",
                       label="Highest SRS (bottleneck)"),
        mpatches.Patch(facecolor=cmap(0.55), edgecolor="#E2E8F0",
                       label="Moderate SRS"),
        mpatches.Patch(facecolor=cmap(0.32), edgecolor="#E2E8F0",
                       label="Lowest SRS (terminal)"),
        Line2D([0], [0], color="#DC2626", linewidth=3, label="r >= 0.99 (CRITICAL)"),
        Line2D([0], [0], color="#F97316", linewidth=2, label="r >= 0.95 (HIGH)"),
        Line2D([0], [0], color="#64748B", linewidth=1.5, label="r < 0.95 (MODERATE)"),
    ]
    ax.legend(
        handles=legend_elements, loc="upper right", fontsize=7.5,
        facecolor="#1E293B", edgecolor="#334155", labelcolor="#E2E8F0",
        framealpha=0.9,
    )

    ax.set_title(
        "Day 18 -- Pipeline DAG: Betweenness Centrality and Cascade Risk\n"
        "Node size/colour = Structural Risk Score  |  Edge colour/width = Day 15 Pearson r",
        fontsize=11, color="#F8FAFC", pad=14, fontweight="bold",
    )
    ax.text(
        0.5, -0.08,
        "[1] Bearing  -->  [2] Shaft  -->  [3] Motor Housing  -->  [4] Coupling  -->  [5] Gearbox",
        transform=ax.transAxes, fontsize=8, color="#94A3B8", ha="center",
    )
    ax.axis("off")
    plt.tight_layout(pad=1.5)

    out = os.path.join(PLOTS_DIR, "dag_centrality_plot.png")
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"    [PNG] Saved: {out}")


# ---------------------------------------------------------------------------
# STEP 6 -- Optional DB MTBF enrichment
# ---------------------------------------------------------------------------
def try_load_db_mtbf() -> dict:
    """
    Load empirical MTBF from failure_log if manufacturing.db exists.
    Returns {component_name: empirical_mtbf_hours} or {} on failure.
    """
    result = {}
    if not os.path.exists(DB_PATH):
        return result
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        sql = (
            "SELECT c.component_name,"
            " COUNT(fl.failure_id) AS n_failures,"
            " SUM(fl.ttf_hours) AS max_age_h"
            " FROM failure_log fl"
            " JOIN components c ON c.component_id = fl.component_id"
            " GROUP BY c.component_name"
        )
        df = pd.read_sql_query(sql, conn)
        conn.close()
        for _, row in df.iterrows():
            if row["n_failures"] > 0 and row["max_age_h"]:
                result[row["component_name"]] = round(
                    row["max_age_h"] / row["n_failures"], 1
                )
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    print("\nBuilding DAG ...")
    G = build_pipeline_dag()

    print("Computing centrality metrics ...")
    df = compute_centrality_metrics(G)

    print_console_report(df, G)

    print("\nExporting CSVs ...")
    export_csvs(df)

    print("\nRendering DAG visualisation ...")
    plot_dag(df, G)

    db_mtbf = try_load_db_mtbf()
    if db_mtbf:
        print("\n[DB] Empirical MTBF vs Weibull analytical MTBF:")
        for comp in PIPELINE_ORDER:
            analytical = G.nodes[comp]["mtbf_hours"]
            empirical  = db_mtbf.get(comp, float("nan"))
            delta      = (
                abs(analytical - empirical)
                if not math.isnan(empirical)
                else float("nan")
            )
            print(
                f"    {comp:<16}  Weibull={analytical:>7.1f}h"
                f"  DB={empirical:>7.1f}h  |Delta|={delta:>7.1f}h"
            )

    print("\nDay 18 complete.\n")


if __name__ == "__main__":
    main()
