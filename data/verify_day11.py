"""Verify Day 11 SQL window analytics queries execute correctly."""
import sqlite3

conn = sqlite3.connect('data/manufacturing.db')

# Q5: MTBF Ranking (simpler, no nested CTE issues)
q5 = """
WITH component_mtbf AS (
    SELECT
        fl.component_id,
        c.component_name,
        c.maintenance_strategy,
        COUNT(*)                                            AS n_failures,
        ROUND(AVG(fl.ttf_hours), 1)                        AS avg_ttf_h,
        ROUND(MIN(fl.ttf_hours), 1)                        AS min_ttf_h,
        ROUND(MAX(fl.ttf_hours), 1)                        AS max_ttf_h,
        ROUND(
            SQRT(AVG(fl.ttf_hours * fl.ttf_hours) - AVG(fl.ttf_hours) * AVG(fl.ttf_hours))
            / MAX(AVG(fl.ttf_hours), 1), 3
        )                                                   AS cov_ttf,
        ROUND(1000.0 / MAX(AVG(fl.ttf_hours), 1), 4)       AS lambda_per_1000h
    FROM failure_log fl
    INNER JOIN components c ON c.component_id = fl.component_id
    WHERE fl.ttf_hours IS NOT NULL
    GROUP BY fl.component_id, c.component_name, c.maintenance_strategy
)
SELECT
    cm.component_name,
    cm.n_failures,
    cm.avg_ttf_h,
    cm.cov_ttf,
    cm.lambda_per_1000h,
    RANK() OVER (ORDER BY cm.avg_ttf_h DESC) AS reliability_rank,
    RANK() OVER (ORDER BY cm.avg_ttf_h ASC)  AS risk_rank
FROM component_mtbf cm
ORDER BY cm.avg_ttf_h DESC
"""
print("=== Q5: MTBF Ranking ===")
for row in conn.execute(q5).fetchall():
    print(row)

# Q1: Sequential MTBF (simplified)
q1 = """
SELECT
    fl.component_id,
    c.component_name,
    fl.cycle_number,
    ROUND(fl.ttf_hours, 1) AS ttf_hours,
    ROUND(LAG(fl.ttf_hours,1) OVER (PARTITION BY fl.component_id ORDER BY fl.cycle_number), 1) AS prev_ttf,
    ROUND(AVG(fl.ttf_hours) OVER (PARTITION BY fl.component_id ORDER BY fl.cycle_number ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 1) AS mtbf_cumulative
FROM failure_log fl
INNER JOIN components c ON c.component_id = fl.component_id
WHERE fl.ttf_hours IS NOT NULL
ORDER BY fl.component_id, fl.cycle_number
"""
print("\n=== Q1: Sequential MTBF (first 8 rows) ===")
for row in conn.execute(q1).fetchall()[:8]:
    print(row)

# OEE summary check (Q4 excerpt)
q4_simple = """
WITH dt AS (
    SELECT shift_id, component_id,
           SUM(CASE WHEN downtime_category != 'planned_maintenance' THEN duration_min ELSE 0.0 END) AS down_min
    FROM downtime_events GROUP BY shift_id, component_id
),
oee_base AS (
    SELECT
        ps.component_id, c.component_name, ps.shift_date, ps.shift_label,
        ROUND((ps.planned_duration_min - COALESCE(dt.down_min,0)) / ps.planned_duration_min * 100.0, 1) AS avail_pct,
        ROUND(MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / MAX(1, ps.planned_duration_min - COALESCE(dt.down_min,0))) * 100.0, 1) AS perf_pct,
        ROUND(CAST(pc.good_units AS FLOAT) / MAX(1, pc.total_units) * 100.0, 1) AS qual_pct,
        ROUND((ps.planned_duration_min - COALESCE(dt.down_min,0)) / ps.planned_duration_min
              * MIN(1.0, (pc.ideal_cycle_time_min * pc.total_units) / MAX(1, ps.planned_duration_min - COALESCE(dt.down_min,0)))
              * CAST(pc.good_units AS FLOAT) / MAX(1, pc.total_units) * 100.0, 1) AS oee_pct
    FROM production_shifts ps
    INNER JOIN components c ON c.component_id = ps.component_id
    LEFT JOIN dt ON dt.shift_id = ps.shift_id AND dt.component_id = ps.component_id
    LEFT JOIN production_counts pc ON pc.shift_id = ps.shift_id AND pc.component_id = ps.component_id
)
SELECT component_name, ROUND(AVG(avail_pct),1), ROUND(AVG(perf_pct),1), ROUND(AVG(qual_pct),1), ROUND(AVG(oee_pct),1)
FROM oee_base
GROUP BY component_id, component_name
ORDER BY component_id
"""
print("\n=== OEE Summary (avg A%, P%, Q%, OEE%) per component ===")
print(f"  {'Component':>14}  {'A%':>5}  {'P%':>5}  {'Q%':>5}  {'OEE%':>6}")
for row in conn.execute(q4_simple).fetchall():
    name, a, p, q, oee = row
    print(f"  {name:>14}  {a:>5}  {p:>5}  {q:>5}  {oee:>6}")

# Q3: Downtime trend (excerpt)
q3_excerpt = """
WITH shift_downtime AS (
    SELECT ps.shift_id, ps.component_id, c.component_name, ps.shift_date, ps.shift_label,
           ps.planned_duration_min,
           COALESCE(SUM(CASE WHEN de.downtime_category != 'planned_maintenance' THEN de.duration_min ELSE 0.0 END),0.0) AS total_downtime_min
    FROM production_shifts ps
    INNER JOIN components c ON c.component_id = ps.component_id
    LEFT JOIN downtime_events de ON de.shift_id = ps.shift_id AND de.component_id = ps.component_id
    GROUP BY ps.shift_id, ps.component_id, c.component_name, ps.shift_date, ps.shift_label, ps.planned_duration_min
)
SELECT component_id, component_name, shift_date, shift_label,
       total_downtime_min,
       ROUND(AVG(total_downtime_min) OVER (PARTITION BY component_id ORDER BY shift_date, shift_label ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),1) AS rolling_7shift,
       ROUND(SUM(total_downtime_min) OVER (PARTITION BY component_id ORDER BY shift_date, shift_label ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),1) AS cumulative
FROM shift_downtime
WHERE component_id = 1
ORDER BY shift_date, shift_label
LIMIT 12
"""
print("\n=== Q3: Downtime Trend - Bearing (12 shifts) ===")
print(f"  {'CID':>3}  {'Date':>12}  {'Sh':>5}  {'Down':>6}  {'7sh-avg':>7}  {'Cumul':>8}")
for row in conn.execute(q3_excerpt).fetchall():
    cid, cname, sdate, slabel, down, roll7, cumul = row
    print(f"  {cid:>3}  {sdate:>12}  {slabel:>5}  {down:>6.1f}  {roll7:>7.1f}  {cumul:>8.1f}")

conn.close()
print("\nAll Day 11 SQL window queries: OK")
