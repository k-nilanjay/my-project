"""
topology.py — Manufacturing Analytics FYP
==========================================
Directed Acyclic Graph (DAG) for the 5-Component Series Pipeline
Day 5 — Phase 1, Sub-phase 1.2

PURPOSE
-------
Encode the physical dependency chain:

    [Bearing] ──► [Shaft] ──► [Motor Housing] ──► [Coupling] ──► [Gearbox]

into a programmatic DAG so that:
  1. simulate.py can query upstream temperature to apply Arrhenius cascade logic.
  2. failure propagation order (Bearing → ... → Gearbox) is a runtime query, not
     hard-coded in multiple modules.
  3. series_system_reliability() in reliability.py has a canonical component
     ordering to produce consistent, reproducible output dictionaries.

DESIGN DECISIONS
----------------
* Pure-Python dict structure — no external graph library (networkx) needed for a
  5-node linear chain. Avoids adding a heavy dependency at Phase 1.
* Adjacency-list representation: PIPELINE_GRAPH maps each node to its immediate
  downstream successor(s). A linear chain has at most one successor per node.
* Component metadata (β, η, Ea, sensor type) lives in reliability.py's
  COMPONENT_WEIBULL_PARAMS. This module holds only topology + position information
  to avoid circular imports.
* Position numbering (1–5) is the canonical ordering used in:
  - sql/seed.sql (component_id == position)
  - kpi.py (system OEE bottleneck reporting)
  - simulate.py (cascade propagation loop)

CASCADE FAILURE LOGIC (Day 1, locked)
--------------------------------------
Failure propagates DOWNSTREAM along the series chain:
    Bearing seizure  → Shaft cannot rotate
    Shaft failure    → Motor Housing overheats (no cooling airflow)
    Motor Housing OT → Coupling shear (no driven shaft)
    Coupling failure → Gearbox starved of input torque

Series reliability block:
    R_system(t) = ∏ R_i(t)   [Day 1, locked — from reliability.py]

Cascade downtime tagging rule (Day 2, locked — from kpi.py):
    When component at position N fails, all components at positions N+1 through 5
    receive a concurrent downtime_event with downtime_category = 'cascade_upstream'.

SQL DATA REQUIREMENTS
---------------------
This module does NOT read from the database directly.
It provides the static topology that ETL and simulation pipelines reference.

    Table consumed (read-only lookup, via simulate.py / etl.py):
        components.component_id    INTEGER — matches COMPONENT_POSITIONS values
        components.position        INTEGER — must equal COMPONENT_POSITIONS[name]
"""

from __future__ import annotations

from typing import Optional


# =============================================================================
# CANONICAL COMPONENT ORDERING
# =============================================================================

# Ordered list — index 0 is the most upstream (first in chain).
# This ordering drives simulation loop iteration and cascade propagation.
PIPELINE_ORDER: list[str] = [
    "Bearing",        # position 1 — most upstream; primary failure initiator
    "Shaft",          # position 2
    "Motor Housing",  # position 3 — thermally sensitive; Arrhenius-dominated
    "Coupling",       # position 4
    "Gearbox",        # position 5 — most downstream; oil/gear-pitting failure mode
]

# Map component name → 1-indexed position (matches sql/seed.sql component_id)
COMPONENT_POSITIONS: dict[str, int] = {
    name: idx + 1 for idx, name in enumerate(PIPELINE_ORDER)
}

# Reverse map: position → component name (useful for cascade propagation lookups)
POSITION_TO_COMPONENT: dict[int, str] = {
    pos: name for name, pos in COMPONENT_POSITIONS.items()
}


# =============================================================================
# ADJACENCY LIST — DIRECTED ACYCLIC GRAPH
# =============================================================================
# Each key is a node; its value is the list of immediate downstream successors.
# In a linear chain each node has at most one successor.
# The terminal node (Gearbox) maps to an empty list.
#
# Format: { upstream_node: [downstream_node, ...] }
#
# DAG property guarantee: no cycles possible in a strict linear chain.
# Adding a return path (e.g., feedback sensor from Gearbox to Bearing) would
# violate the DAG assumption and would require a cycle-detection pass.

PIPELINE_GRAPH: dict[str, list[str]] = {
    "Bearing":       ["Shaft"],
    "Shaft":         ["Motor Housing"],
    "Motor Housing": ["Coupling"],
    "Coupling":      ["Gearbox"],
    "Gearbox":       [],           # terminal node — no downstream successor
}

# Reverse adjacency: map each node to its immediate upstream predecessor(s).
# Useful for Arrhenius cascade: Motor Housing needs Bearing + Shaft temperatures.
PIPELINE_GRAPH_REVERSED: dict[str, list[str]] = {
    name: [] for name in PIPELINE_ORDER
}
for _upstream, _downstream_list in PIPELINE_GRAPH.items():
    for _ds in _downstream_list:
        PIPELINE_GRAPH_REVERSED[_ds].append(_upstream)


# =============================================================================
# COMPONENT METADATA — TOPOLOGY-LEVEL ANNOTATIONS
# =============================================================================
# Detailed Weibull params (β, η, Ea) live in reliability.py::COMPONENT_WEIBULL_PARAMS.
# This dict stores topology-layer metadata: failure mode, primary sensor type,
# and which failure modes have a thermal (Arrhenius) component.

COMPONENT_TOPOLOGY_META: dict[str, dict] = {
    "Bearing": {
        "position":             1,
        "primary_failure_mode": "rolling_element_fatigue",
        "secondary_failure_mode": "lubricant_breakdown",
        "primary_sensor_type":  "vibration",            # sensor_id 11 in seed.sql
        "arrhenius_applicable": True,                    # Ea = 0.80 eV
        "maintenance_strategy": "PM",
        "cascade_trigger":      True,   # a Bearing failure initiates cascade
        "cascade_recipient":    False,  # Bearing has no upstream component
    },
    "Shaft": {
        "position":             2,
        "primary_failure_mode": "fatigue_imbalance",
        "secondary_failure_mode": "torsional_stress",
        "primary_sensor_type":  "vibration",            # sensor_id 21
        "arrhenius_applicable": False,                   # Ea = NULL; fatigue-dominant
        "maintenance_strategy": "CBM",
        "cascade_trigger":      True,
        "cascade_recipient":    True,   # can receive cascade from Bearing
    },
    "Motor Housing": {
        "position":             3,
        "primary_failure_mode": "winding_insulation_degradation",
        "secondary_failure_mode": "thermal_overstress",
        "primary_sensor_type":  "temperature",          # sensor_id 31
        "arrhenius_applicable": True,                    # Ea = 1.00 eV (highest)
        "maintenance_strategy": "CBM",
        "cascade_trigger":      True,
        "cascade_recipient":    True,
    },
    "Coupling": {
        "position":             4,
        "primary_failure_mode": "elastomer_ageing",
        "secondary_failure_mode": "misalignment",
        "primary_sensor_type":  "vibration",            # sensor_id 41 (2× harmonic)
        "arrhenius_applicable": True,                    # Ea = 0.60 eV
        "maintenance_strategy": "CBM",
        "cascade_trigger":      True,
        "cascade_recipient":    True,
    },
    "Gearbox": {
        "position":             5,
        "primary_failure_mode": "gear_tooth_pitting",
        "secondary_failure_mode": "oil_oxidation",
        "primary_sensor_type":  "vibration",            # sensor_id 51 + oil_debris 52
        "arrhenius_applicable": True,                    # Ea = 0.70 eV
        "maintenance_strategy": "PM_CBM",
        "cascade_trigger":      False,   # Gearbox is terminal — no further downstream
        "cascade_recipient":    True,
    },
}


# =============================================================================
# GRAPH TRAVERSAL UTILITIES
# =============================================================================

def get_downstream_components(component_name: str) -> list[str]:
    """
    Return all components downstream of the given component (inclusive of
    immediate successor and all further successors in the chain).

    Used by simulate.py cascade propagation: when a component fails, all
    components returned by this function receive a cascade_upstream downtime event.

    Parameters
    ----------
    component_name : str — name of the failed component (must be in PIPELINE_GRAPH)

    Returns
    -------
    list[str] — ordered list of downstream component names (nearest first).
                Empty list if component_name is the terminal node (Gearbox).

    Example
    -------
    >>> get_downstream_components("Bearing")
    ['Shaft', 'Motor Housing', 'Coupling', 'Gearbox']
    >>> get_downstream_components("Gearbox")
    []
    """
    _validate_component_name(component_name)

    downstream: list[str] = []
    current = component_name

    while True:
        successors = PIPELINE_GRAPH.get(current, [])
        if not successors:
            break
        next_node = successors[0]   # linear chain: exactly one successor
        downstream.append(next_node)
        current = next_node

    return downstream


def get_upstream_components(component_name: str) -> list[str]:
    """
    Return all components upstream of the given component (from the most
    upstream ancestor down to the immediate predecessor).

    Used by simulate.py Arrhenius temperature injection: a thermally stressed
    component may receive elevated heat from upstream components' waste heat.

    Parameters
    ----------
    component_name : str — query component name

    Returns
    -------
    list[str] — ordered list of upstream component names (most upstream first).
                Empty list if component_name is Bearing (no upstream predecessor).

    Example
    -------
    >>> get_upstream_components("Motor Housing")
    ['Bearing', 'Shaft']
    >>> get_upstream_components("Bearing")
    []
    """
    _validate_component_name(component_name)

    position = COMPONENT_POSITIONS[component_name]
    # All components with a lower position number are upstream
    return [POSITION_TO_COMPONENT[p] for p in range(1, position)]


def get_cascade_affected_positions(failed_position: int) -> list[int]:
    """
    Given the position of a failed component, return the positions of all
    components that receive a cascade_upstream downtime event.

    This implements the Day 2 cascade tagging rule:
        "When component at position N fails, all components at positions N+1
         through 5 receive cascade_upstream downtime."

    Parameters
    ----------
    failed_position : int — 1-indexed position of the failing component (1–5)

    Returns
    -------
    list[int] — 1-indexed positions affected by cascade (empty if Gearbox fails)

    Example
    -------
    >>> get_cascade_affected_positions(1)   # Bearing fails
    [2, 3, 4, 5]
    >>> get_cascade_affected_positions(5)   # Gearbox fails — terminal
    []
    """
    if failed_position < 1 or failed_position > len(PIPELINE_ORDER):
        raise ValueError(
            f"failed_position must be in [1, {len(PIPELINE_ORDER)}]; "
            f"received {failed_position}"
        )
    return list(range(failed_position + 1, len(PIPELINE_ORDER) + 1))


def topological_sort() -> list[str]:
    """
    Return the components in topological order (upstream → downstream).

    For a linear DAG this is simply PIPELINE_ORDER, but this function makes the
    dependency semantics explicit and allows simulate.py to call it once on startup
    rather than assuming the order of a dict literal.

    Returns
    -------
    list[str] — component names in topological order (Bearing first, Gearbox last)
    """
    return list(PIPELINE_ORDER)


def is_arrhenius_applicable(component_name: str) -> bool:
    """
    Return True if the component has a thermal Arrhenius failure mode.

    Shaft is the only component for which this returns False (fatigue-dominant;
    no Ea value in the database — activation_energy_ev = NULL in seed.sql).

    Parameters
    ----------
    component_name : str

    Returns
    -------
    bool
    """
    _validate_component_name(component_name)
    return COMPONENT_TOPOLOGY_META[component_name]["arrhenius_applicable"]


def get_component_at_position(position: int) -> str:
    """
    Return the component name at the given 1-indexed pipeline position.

    Parameters
    ----------
    position : int — pipeline position (1 = Bearing, 5 = Gearbox)

    Returns
    -------
    str — component name
    """
    if position not in POSITION_TO_COMPONENT:
        raise ValueError(
            f"Position must be in [1, {len(PIPELINE_ORDER)}]; received {position}"
        )
    return POSITION_TO_COMPONENT[position]


def pipeline_summary() -> list[dict]:
    """
    Return a list of dicts summarising the full pipeline topology.

    Intended for debug printing and for simulate.py startup diagnostics.

    Returns
    -------
    list[dict] — one dict per component, in topological order.
        Keys: position, name, upstream, downstream, arrhenius_applicable,
              primary_failure_mode, maintenance_strategy
    """
    summary = []
    for name in PIPELINE_ORDER:
        meta = COMPONENT_TOPOLOGY_META[name]
        upstream   = get_upstream_components(name)
        downstream = get_downstream_components(name)
        summary.append({
            "position":              meta["position"],
            "name":                  name,
            "upstream":              upstream   if upstream   else ["—"],
            "downstream":            downstream if downstream else ["—"],
            "arrhenius_applicable":  meta["arrhenius_applicable"],
            "primary_failure_mode":  meta["primary_failure_mode"],
            "maintenance_strategy":  meta["maintenance_strategy"],
        })
    return summary


# =============================================================================
# PRIVATE HELPERS
# =============================================================================

def _validate_component_name(name: str) -> None:
    """Raise ValueError if name is not a recognised pipeline component."""
    if name not in PIPELINE_GRAPH:
        valid = list(PIPELINE_GRAPH.keys())
        raise ValueError(
            f"Unknown component '{name}'. Valid options: {valid}"
        )


# =============================================================================
# MODULE SELF-TEST (run directly: python topology.py)
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PIPELINE TOPOLOGY — DAG SELF-TEST")
    print("=" * 60)

    rows = pipeline_summary()
    header = f"{'Pos':>3}  {'Component':<16}  {'Upstream':<20}  {'Downstream':<35}  {'Arrhenius':>9}  {'Strategy'}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['position']:>3}  "
            f"{row['name']:<16}  "
            f"{', '.join(row['upstream']):<20}  "
            f"{', '.join(row['downstream']):<35}  "
            f"{str(row['arrhenius_applicable']):>9}  "
            f"{row['maintenance_strategy']}"
        )

    print()
    print("Cascade test — Bearing fails (position 1):")
    affected = get_cascade_affected_positions(1)
    print(f"  Cascade-affected positions: {affected}")
    print(f"  Component names: {[POSITION_TO_COMPONENT[p] for p in affected]}")

    print()
    print("Topological sort:", topological_sort())
    print()
    print("Upstream of Motor Housing:", get_upstream_components("Motor Housing"))
    print("Downstream of Shaft:      ", get_downstream_components("Shaft"))
    print()
    print("Arrhenius applicable per component:")
    for comp in PIPELINE_ORDER:
        print(f"  {comp:<16}: {is_arrhenius_applicable(comp)}")
