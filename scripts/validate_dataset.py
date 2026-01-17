#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd
import yaml


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_config(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def md_h(title: str, level: int = 2) -> str:
    return f"{'#' * level} {title}\n"


def table_md(rows: List[Tuple[str, Any]]) -> str:
    out = "| Metric | Value |\n|---|---|\n"
    for k, v in rows:
        out += f"| {k} | {v} |\n"
    return out + "\n"


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    cfg_path = project_dir / "configs" / "citygrid_generation.yaml"
    if len(os.sys.argv) >= 2:
        cfg_path = Path(os.sys.argv[1]).resolve()

    cfg = load_config(cfg_path)

    db_path = Path(cfg["output"]["sqlite_path"])
    if not db_path.is_absolute():
        db_path = (project_dir / db_path).resolve()

    out_path = (project_dir / "outputs" / "validation_report.md").resolve()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")

    report = ""
    report += "# CityGrid - Validation Report\n\n"
    report += f"- DB: `{db_path}`\n"
    report += f"- Generated with config: `{cfg_path}`\n\n"

    # FK check
    fk = conn.execute("PRAGMA foreign_key_check;").fetchall()
    report += md_h("Foreign keys", 2)
    report += f"- foreign_key_check rows: {len(fk)}\n\n"

    # bbox check
    b = cfg["geography"]["city_bounds"]
    lat_min, lat_max = float(b["lat_min"]), float(b["lat_max"])
    lon_min, lon_max = float(b["lon_min"]), float(b["lon_max"])

    report += md_h("Geography bbox", 2)
    q1 = """
    SELECT
      SUM(CASE WHEN lat < ? OR lat > ? OR lon < ? OR lon > ? THEN 1 ELSE 0 END) AS objects_out
    FROM city_objects;
    """
    objects_out = conn.execute(q1, (lat_min, lat_max, lon_min, lon_max)).fetchone()[0]

    q2 = """
    SELECT
      SUM(CASE WHEN lat < ? OR lat > ? OR lon < ? OR lon > ? THEN 1 ELSE 0 END) AS events_out
    FROM municipal_events;
    """
    events_out = conn.execute(q2, (lat_min, lat_max, lon_min, lon_max)).fetchone()[0]

    report += table_md([
        ("objects_out_of_bbox", objects_out),
        ("events_out_of_bbox", events_out),
    ])

    # counts
    report += md_h("Row counts", 2)
    tables = [
        "districts", "city_objects", "sensors", "smart_meters",
        "municipal_events", "citizen_requests", "public_transport_trips",
        "sensor_readings", "meter_readings",
    ]
    rows = []
    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        rows.append((t, n))
    report += "| Table | Rows |\n|---|---|\n" + "\n".join([f"| {t} | {n} |" for t, n in rows]) + "\n\n"

    # quality checks
    report += md_h("Quality flags + anomaly_score", 2)
    q = """
    SELECT
      SUM(CASE WHEN quality_flag='missing' THEN 1 ELSE 0 END) AS n_missing,
      SUM(CASE WHEN quality_flag='suspect' THEN 1 ELSE 0 END) AS n_suspect,
      COUNT(*) AS n_total,
      SUM(CASE WHEN quality_flag IN ('ok','missing') AND anomaly_score <> 0.0 THEN 1 ELSE 0 END) AS bad_zero_rule,
      SUM(CASE WHEN quality_flag='suspect' AND anomaly_score <= 0.0 THEN 1 ELSE 0 END) AS bad_suspect_rule
    FROM sensor_readings;
    """
    n_missing, n_suspect, n_total, bad_zero_rule, bad_suspect_rule = conn.execute(q).fetchone()
    miss_share = (n_missing / n_total) if n_total else 0.0
    susp_share = (n_suspect / n_total) if n_total else 0.0
    report += table_md([
        ("sensor_readings_total", n_total),
        ("missing_count", n_missing),
        ("suspect_count", n_suspect),
        ("missing_share", f"{miss_share:.4f}"),
        ("suspect_share", f"{susp_share:.4f}"),
        ("anomaly_score_nonzero_for_ok_or_missing", bad_zero_rule),
        ("anomaly_score_nonpositive_for_suspect", bad_suspect_rule),
    ])

    # causality A: events -> traffic/noise up during event (district-level proxy via sensors)
    report += md_h("Causality A: events -> traffic/noise", 2)
    # Sample few events (limit 15) and compare avg in same district, in time windows
    ev = pd.read_sql_query("SELECT event_id, district_id, start_ts, end_ts FROM municipal_events ORDER BY event_id LIMIT 15", conn)
    diffs = []
    for _, r in ev.iterrows():
        did = int(r["district_id"])
        start = r["start_ts"]
        end = r["end_ts"]

        # baseline: 24h before start
        q_base = """
        SELECT AVG(sr.value) AS v
        FROM sensor_readings sr
        JOIN sensors s ON s.sensor_id = sr.sensor_id
        JOIN city_objects o ON o.object_id = s.object_id
        WHERE o.district_id = ?
          AND s.sensor_type = ?
          AND sr.quality_flag = 'ok'
          AND sr.ts >= datetime(?, '-24 hours')
          AND sr.ts < ?;
        """
        q_dur = """
        SELECT AVG(sr.value) AS v
        FROM sensor_readings sr
        JOIN sensors s ON s.sensor_id = sr.sensor_id
        JOIN city_objects o ON o.object_id = s.object_id
        WHERE o.district_id = ?
          AND s.sensor_type = ?
          AND sr.quality_flag = 'ok'
          AND sr.ts >= ?
          AND sr.ts <= ?;
        """
        base_traffic = conn.execute(q_base, (did, "traffic_intensity", start, start)).fetchone()[0]
        dur_traffic = conn.execute(q_dur, (did, "traffic_intensity", start, end)).fetchone()[0]
        base_noise = conn.execute(q_base, (did, "noise_db", start, start)).fetchone()[0]
        dur_noise = conn.execute(q_dur, (did, "noise_db", start, end)).fetchone()[0]

        if base_traffic is None or dur_traffic is None or base_noise is None or dur_noise is None:
            continue
        diffs.append((dur_traffic - base_traffic, dur_noise - base_noise))

    if diffs:
        dt = float(np.mean([d[0] for d in diffs]))
        dn = float(np.mean([d[1] for d in diffs]))
        report += table_md([
            ("sample_events", len(diffs)),
            ("avg_delta_traffic_during_minus_before", f"{dt:.3f}"),
            ("avg_delta_noise_during_minus_before", f"{dn:.3f}"),
        ])
    else:
        report += "- Not enough data to compute event deltas (unexpected)\n\n"

    # causality: after events -> more noise_complaint + parking_issue (district-level)
    report += md_h("Causality A: after events -> complaints", 2)
    q_after = """
    WITH ev AS (
      SELECT district_id, start_ts, end_ts
      FROM municipal_events
    ),
    win AS (
      SELECT
        e.district_id AS district_id,
        datetime(e.end_ts) AS a0,
        datetime(e.end_ts, '+24 hours') AS a1,
        datetime(e.start_ts, '-24 hours') AS b0,
        datetime(e.start_ts) AS b1
      FROM ev e
    )
    SELECT
      SUM(CASE WHEN cr.category IN ('noise_complaint','parking_issue') AND cr.created_ts >= w.a0 AND cr.created_ts < w.a1 THEN 1 ELSE 0 END) AS after_cnt,
      SUM(CASE WHEN cr.category IN ('noise_complaint','parking_issue') AND cr.created_ts >= w.b0 AND cr.created_ts < w.b1 THEN 1 ELSE 0 END) AS before_cnt
    FROM win w
    JOIN citizen_requests cr ON cr.district_id = w.district_id;
    """
    after_cnt, before_cnt = conn.execute(q_after).fetchone()
    report += table_md([
        ("complaints_after_events_24h", after_cnt),
        ("complaints_before_events_24h", before_cnt),
    ])

    # transport punctuality
    report += md_h("Transport punctuality (routes)", 2)
    q_routes = """
    SELECT route_no,
           AVG(delay_minutes) AS avg_delay,
           AVG(CASE WHEN delay_minutes=0 THEN 1.0 ELSE 0.0 END) AS on_time_share,
           COUNT(*) AS trips
    FROM public_transport_trips
    GROUP BY route_no
    ORDER BY trips DESC
    LIMIT 10;
    """
    df_routes = pd.read_sql_query(q_routes, conn)
    report += df_routes.to_markdown(index=False) + "\n\n"

    # pm25 vs air_quality requests (rough signal)
    report += md_h("pm25 vs air_quality requests (district-level hourly proxy)", 2)
    # Use pm25 sensor readings aggregated by hour and district, correlate with air_quality counts
    q_pm = """
    WITH pm AS (
      SELECT o.district_id AS district_id,
             substr(sr.ts, 1, 13) || ':00:00' AS hour_ts,
             AVG(sr.value) AS pm25_avg
      FROM sensor_readings sr
      JOIN sensors s ON s.sensor_id = sr.sensor_id
      JOIN city_objects o ON o.object_id = s.object_id
      WHERE s.sensor_type = 'pm25' AND sr.quality_flag='ok'
      GROUP BY o.district_id, hour_ts
    ),
    rq AS (
      SELECT district_id,
             substr(created_ts, 1, 13) || ':00:00' AS hour_ts,
             SUM(CASE WHEN category='air_quality' THEN 1 ELSE 0 END) AS airq_cnt
      FROM citizen_requests
      GROUP BY district_id, hour_ts
    )
    SELECT pm.district_id, pm.hour_ts, pm.pm25_avg, COALESCE(rq.airq_cnt,0) AS airq_cnt
    FROM pm
    LEFT JOIN rq ON rq.district_id = pm.district_id AND rq.hour_ts = pm.hour_ts
    ORDER BY pm.pm25_avg DESC
    LIMIT 20;
    """
    df_pm = pd.read_sql_query(q_pm, conn)
    report += df_pm.to_markdown(index=False) + "\n\n"

    report += md_h("Control SQL queries (non-empty expected)", 2)
    report += """
-- Top districts by requests (last 30 days from min date)
SELECT d.name, COUNT(*) AS req_cnt
FROM citizen_requests cr
JOIN districts d ON d.district_id = cr.district_id
WHERE cr.created_ts >= (SELECT datetime(MIN(created_ts), '+0 days') FROM citizen_requests)
  AND cr.created_ts <  (SELECT datetime(MIN(created_ts), '+30 days') FROM citizen_requests)
GROUP BY d.name
ORDER BY req_cnt DESC
LIMIT 10;

-- Traffic and noise before vs during event (sample event_id=1)
SELECT
  AVG(CASE WHEN s.sensor_type='traffic_intensity' THEN sr.value END) AS traffic_avg,
  AVG(CASE WHEN s.sensor_type='noise_db' THEN sr.value END) AS noise_avg
FROM sensor_readings sr
JOIN sensors s ON s.sensor_id=sr.sensor_id
JOIN city_objects o ON o.object_id=s.object_id
JOIN municipal_events e ON e.district_id=o.district_id
WHERE e.event_id=1
  AND sr.ts BETWEEN e.start_ts AND e.end_ts
  AND sr.quality_flag='ok';

-- Route punctuality
SELECT route_no,
       AVG(delay_minutes) AS avg_delay,
       AVG(CASE WHEN delay_minutes=0 THEN 1.0 ELSE 0.0 END) AS on_time_share
FROM public_transport_trips
GROUP BY route_no
ORDER BY on_time_share DESC
LIMIT 10;

-- pm25 high hours vs air_quality requests
WITH pm AS (
  SELECT o.district_id AS district_id,
         substr(sr.ts, 1, 13) || ':00:00' AS hour_ts,
         AVG(sr.value) AS pm25_avg
  FROM sensor_readings sr
  JOIN sensors s ON s.sensor_id=sr.sensor_id
  JOIN city_objects o ON o.object_id=s.object_id
  WHERE s.sensor_type='pm25' AND sr.quality_flag='ok'
  GROUP BY o.district_id, hour_ts
)
SELECT pm.district_id,
       SUM(CASE WHEN pm.pm25_avg > 35 THEN 1 ELSE 0 END) AS hours_pm25_gt_35,
       SUM(CASE WHEN cr.category='air_quality' THEN 1 ELSE 0 END) AS airq_requests
FROM pm
LEFT JOIN citizen_requests cr
  ON cr.district_id=pm.district_id
 AND substr(cr.created_ts, 1, 13) || ':00:00' = pm.hour_ts
GROUP BY pm.district_id
ORDER BY hours_pm25_gt_35 DESC;
"""

    out_path.write_text(report, encoding="utf-8")
    conn.close()

    print(f"OK: saved {out_path}")

if __name__ == "__main__":
    main()
