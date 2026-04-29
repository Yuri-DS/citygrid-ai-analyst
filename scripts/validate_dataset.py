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
    ensure_dir(out_path.parent)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")

    report = ""
    report += "# CityGrid - Validation Report\n\n"
    report += f"- DB: `{db_path}`\n"
    report += f"- Generated with config: `{cfg_path}`\n"
    report += f"- Scale: `{cfg['generation']['scale']}`\n"
    report += f"- Period: {cfg['generation']['days']} days\n\n"

    # ===== INTEGRITY CHECKS =====
    report += md_h("1. Data Integrity", 2)

    # Foreign keys
    fk = conn.execute("PRAGMA foreign_key_check;").fetchall()
    report += md_h("Foreign Key Violations", 3)
    report += table_md([
        ("foreign_key_violations", len(fk)),
    ])
    if fk:
        report += f"⚠️ **WARNING**: {len(fk)} foreign key violations detected!\n\n"
    else:
        report += "✅ All foreign keys valid\n\n"

    # Geography bbox
    b = cfg["geography"]["city_bounds"]
    lat_min, lat_max = float(b["lat_min"]), float(b["lat_max"])
    lon_min, lon_max = float(b["lon_min"]), float(b["lon_max"])

    report += md_h("Geographic Boundaries", 3)

    # Check city_objects
    q_objects = """
    SELECT
      SUM(CASE WHEN lat < ? OR lat > ? OR lon < ? OR lon > ? THEN 1 ELSE 0 END) AS objects_out
    FROM city_objects;
    """
    objects_out = conn.execute(q_objects, (lat_min, lat_max, lon_min, lon_max)).fetchone()[0]

    # Check events
    q_events = """
    SELECT
      SUM(CASE WHEN lat < ? OR lat > ? OR lon < ? OR lon > ? THEN 1 ELSE 0 END) AS events_out
    FROM municipal_events;
    """
    events_out = conn.execute(q_events, (lat_min, lat_max, lon_min, lon_max)).fetchone()[0]

    # Check nodes
    q_nodes = """
    SELECT
      SUM(CASE WHEN lat < ? OR lat > ? OR lon < ? OR lon > ? THEN 1 ELSE 0 END) AS nodes_out
    FROM road_network_nodes;
    """
    nodes_out = conn.execute(q_nodes, (lat_min, lat_max, lon_min, lon_max)).fetchone()[0]

    # Check road segments start/end
    q_roads = """
    SELECT
      SUM(CASE WHEN start_lat < ? OR start_lat > ? OR start_lon < ? OR start_lon > ? 
                 OR end_lat < ? OR end_lat > ? OR end_lon < ? OR end_lon > ? 
              THEN 1 ELSE 0 END) AS roads_out
    FROM city_objects
    WHERE object_type = 'road_segment';
    """
    roads_out = \
    conn.execute(q_roads, (lat_min, lat_max, lon_min, lon_max, lat_min, lat_max, lon_min, lon_max)).fetchone()[0]

    report += table_md([
        ("objects_out_of_bbox", objects_out),
        ("events_out_of_bbox", events_out),
        ("nodes_out_of_bbox", nodes_out),
        ("road_segments_out_of_bbox", roads_out),
    ])

    if objects_out == 0 and events_out == 0 and nodes_out == 0 and roads_out == 0:
        report += "✅ All coordinates within bbox\n\n"
    else:
        report += "⚠️ **WARNING**: Some coordinates outside bbox!\n\n"

    # ===== ROW COUNTS =====
    report += md_h("2. Row Counts", 2)
    tables = [
        "districts", "road_network_nodes", "city_objects", "sensors", "smart_meters",
        "municipal_events", "citizen_requests", "public_transport_trips",
        "sensor_readings", "meter_readings",
    ]
    rows = []
    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        rows.append((t, f"{n:,}"))
    report += "| Table | Rows |\n|---|---|\n" + "\n".join([f"| {t} | {n} |" for t, n in rows]) + "\n\n"

    # Road segments breakdown
    report += md_h("Road Segments Breakdown", 3)
    q_roads_breakdown = """
    SELECT object_type, COUNT(*) AS cnt
    FROM city_objects
    GROUP BY object_type
    ORDER BY cnt DESC;
    """
    df_obj_types = pd.read_sql_query(q_roads_breakdown, conn)
    report += df_obj_types.to_markdown(index=False) + "\n\n"

    road_count = conn.execute("SELECT COUNT(*) FROM city_objects WHERE object_type='road_segment'").fetchone()[0]
    total_count = conn.execute("SELECT COUNT(*) FROM city_objects").fetchone()[0]
    road_pct = (road_count / total_count * 100) if total_count > 0 else 0
    report += f"Road segments: {road_count:,} ({road_pct:.1f}% of all objects)\n\n"

    # ===== ROAD NETWORK VALIDATION =====
    report += md_h("3. Road Network Validation", 2)

    # Node types
    report += md_h("Node Types Distribution", 3)
    q_node_types = """
    SELECT type, COUNT(*) AS cnt
    FROM road_network_nodes
    GROUP BY type;
    """
    df_node_types = pd.read_sql_query(q_node_types, conn)
    report += df_node_types.to_markdown(index=False) + "\n\n"

    # District center connections
    q_dc_nodes = """
    SELECT 
        COUNT(*) AS total_nodes,
        SUM(is_connected_to_district_center) AS district_center_nodes
    FROM road_network_nodes;
    """
    total_nodes, dc_nodes = conn.execute(q_dc_nodes).fetchone()
    report += table_md([
        ("total_nodes", total_nodes),
        ("district_center_nodes", dc_nodes),
    ])

    # Road type distribution
    report += md_h("Road Type Distribution", 3)
    q_road_types = """
    SELECT road_type, COUNT(*) AS cnt, 
           AVG(length_m) AS avg_length_m,
           AVG(max_speed_kmh) AS avg_speed,
           AVG(lanes_count) AS avg_lanes
    FROM city_objects
    WHERE object_type = 'road_segment'
    GROUP BY road_type
    ORDER BY cnt DESC;
    """
    df_road_types = pd.read_sql_query(q_road_types, conn)
    report += df_road_types.to_markdown(index=False) + "\n\n"

    # Road condition distribution
    report += md_h("Road Condition Distribution", 3)
    q_road_cond = """
    SELECT condition, COUNT(*) AS cnt,
           ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM city_objects WHERE object_type='road_segment'), 2) AS pct
    FROM city_objects
    WHERE object_type = 'road_segment'
    GROUP BY condition
    ORDER BY 
        CASE condition 
            WHEN 'good' THEN 1 
            WHEN 'fair' THEN 2 
            WHEN 'poor' THEN 3 
        END;
    """
    df_road_cond = pd.read_sql_query(q_road_cond, conn)
    report += df_road_cond.to_markdown(index=False) + "\n\n"

    # Direction distribution
    report += md_h("Road Direction Distribution", 3)
    q_direction = """
    SELECT direction, COUNT(*) AS cnt
    FROM city_objects
    WHERE object_type = 'road_segment'
    GROUP BY direction;
    """
    df_direction = pd.read_sql_query(q_direction, conn)
    report += df_direction.to_markdown(index=False) + "\n\n"

    # Network connectivity check
    report += md_h("Network Connectivity", 3)
    q_orphan_nodes = """
    SELECT COUNT(DISTINCT rn.node_id) AS orphan_nodes
    FROM road_network_nodes rn
    WHERE NOT EXISTS (
        SELECT 1 FROM city_objects co 
        WHERE co.object_type = 'road_segment' 
        AND (co.from_node_id = rn.node_id OR co.to_node_id = rn.node_id)
    );
    """
    orphan_nodes = conn.execute(q_orphan_nodes).fetchone()[0]

    q_road_nulls = """
    SELECT 
        SUM(CASE WHEN from_node_id IS NULL THEN 1 ELSE 0 END) AS null_from,
        SUM(CASE WHEN to_node_id IS NULL THEN 1 ELSE 0 END) AS null_to
    FROM city_objects
    WHERE object_type = 'road_segment';
    """
    null_from, null_to = conn.execute(q_road_nulls).fetchone()

    report += table_md([
        ("orphan_nodes (not connected)", orphan_nodes),
        ("road_segments_with_null_from_node", null_from or 0),
        ("road_segments_with_null_to_node", null_to or 0),
    ])

    if orphan_nodes == 0 and (null_from or 0) == 0 and (null_to or 0) == 0:
        report += "✅ Network fully connected\n\n"
    else:
        report += "⚠️ **WARNING**: Network has disconnected components!\n\n"

    # ===== QUALITY FLAGS & ANOMALY SCORES =====
    report += md_h("4. Data Quality", 2)

    report += md_h("Quality Flags & Anomaly Scores", 3)
    q_quality = """
    SELECT
      SUM(CASE WHEN quality_flag='missing' THEN 1 ELSE 0 END) AS n_missing,
      SUM(CASE WHEN quality_flag='suspect' THEN 1 ELSE 0 END) AS n_suspect,
      SUM(CASE WHEN quality_flag='ok' THEN 1 ELSE 0 END) AS n_ok,
      COUNT(*) AS n_total,
      SUM(CASE WHEN quality_flag IN ('ok','missing') AND anomaly_score <> 0.0 THEN 1 ELSE 0 END) AS bad_zero_rule,
      SUM(CASE WHEN quality_flag='suspect' AND anomaly_score <= 0.0 THEN 1 ELSE 0 END) AS bad_suspect_rule,
      AVG(CASE WHEN quality_flag='suspect' THEN anomaly_score END) AS avg_suspect_score,
      MAX(CASE WHEN quality_flag='suspect' THEN anomaly_score END) AS max_suspect_score
    FROM sensor_readings;
    """
    n_missing, n_suspect, n_ok, n_total, bad_zero_rule, bad_suspect_rule, avg_suspect_score, max_suspect_score = conn.execute(
        q_quality).fetchone()

    miss_share = (n_missing / n_total) if n_total else 0.0
    susp_share = (n_suspect / n_total) if n_total else 0.0
    ok_share = (n_ok / n_total) if n_total else 0.0

    report += table_md([
        ("sensor_readings_total", f"{n_total:,}"),
        ("ok_count", f"{n_ok:,}"),
        ("missing_count", f"{n_missing:,}"),
        ("suspect_count", f"{n_suspect:,}"),
        ("ok_share", f"{ok_share:.4f}"),
        ("missing_share", f"{miss_share:.4f}"),
        ("suspect_share", f"{susp_share:.4f}"),
        ("avg_suspect_anomaly_score", f"{avg_suspect_score:.4f}" if avg_suspect_score else "N/A"),
        ("max_suspect_anomaly_score", f"{max_suspect_score:.4f}" if max_suspect_score else "N/A"),
    ])

    # Quality rule violations
    report += md_h("Quality Rule Violations", 3)
    report += table_md([
        ("anomaly_score_nonzero_for_ok_or_missing", bad_zero_rule),
        ("anomaly_score_nonpositive_for_suspect", bad_suspect_rule),
    ])

    if bad_zero_rule == 0 and bad_suspect_rule == 0:
        report += "✅ All quality rules respected\n\n"
    else:
        report += "⚠️ **WARNING**: Quality rule violations detected!\n\n"

    # Missing by sensor type
    report += md_h("Missing Data by Sensor Type", 3)
    q_missing_by_type = """
    SELECT s.sensor_type,
           SUM(CASE WHEN sr.quality_flag='missing' THEN 1 ELSE 0 END) AS missing_cnt,
           COUNT(*) AS total_cnt,
           ROUND(100.0 * SUM(CASE WHEN sr.quality_flag='missing' THEN 1 ELSE 0 END) / COUNT(*), 2) AS missing_pct
    FROM sensor_readings sr
    JOIN sensors s ON s.sensor_id = sr.sensor_id
    GROUP BY s.sensor_type;
    """
    df_missing = pd.read_sql_query(q_missing_by_type, conn)
    report += df_missing.to_markdown(index=False) + "\n\n"

    # ===== CAUSALITY CHECKS =====
    report += md_h("5. Causality Validation", 2)

    # A: Events -> Traffic/Noise increase
    report += md_h("A: Events → Traffic & Noise Increase", 3)
    ev = pd.read_sql_query(
        "SELECT event_id, district_id, start_ts, end_ts FROM municipal_events ORDER BY event_id LIMIT 20", conn)
    diffs_traffic = []
    diffs_noise = []

    for _, r in ev.iterrows():
        did = int(r["district_id"])
        start = r["start_ts"]
        end = r["end_ts"]

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

        if base_traffic and dur_traffic:
            diffs_traffic.append(dur_traffic - base_traffic)
        if base_noise and dur_noise:
            diffs_noise.append(dur_noise - base_noise)

    if diffs_traffic and diffs_noise:
        dt_mean = float(np.mean(diffs_traffic))
        dn_mean = float(np.mean(diffs_noise))
        dt_positive_pct = sum(1 for d in diffs_traffic if d > 0) / len(diffs_traffic) * 100
        dn_positive_pct = sum(1 for d in diffs_noise if d > 0) / len(diffs_noise) * 100

        report += table_md([
            ("sample_events_analyzed", len(ev)),
            ("avg_delta_traffic (during - before)", f"{dt_mean:.3f} veh/h"),
            ("avg_delta_noise (during - before)", f"{dn_mean:.3f} dB"),
            ("pct_events_with_traffic_increase", f"{dt_positive_pct:.1f}%"),
            ("pct_events_with_noise_increase", f"{dn_positive_pct:.1f}%"),
        ])

        if dt_mean > 5 and dn_mean > 1:
            report += "✅ Events clearly increase traffic and noise\n\n"
        else:
            report += "⚠️ Weak event impact on metrics\n\n"
    else:
        report += "⚠️ Not enough data to compute event deltas\n\n"

    # B: After events -> More complaints
    report += md_h("B: After Events → Increased Complaints", 3)
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
    increase_pct = ((after_cnt - before_cnt) / before_cnt * 100) if before_cnt > 0 else 0

    report += table_md([
        ("complaints_24h_after_events", after_cnt),
        ("complaints_24h_before_events", before_cnt),
        ("increase_pct", f"{increase_pct:.1f}%"),
    ])

    if after_cnt > before_cnt * 1.2:
        report += "✅ Complaints increase after events (20%+ increase)\n\n"
    else:
        report += "⚠️ Weak complaint increase after events\n\n"

    # C: Cold temperature -> Heating issues
    report += md_h("C: Cold Temperature → Heating Issues", 3)
    q_cold_heating = """
    WITH temp_data AS (
        SELECT substr(sr.ts, 1, 10) AS date,
               AVG(sr.value) AS avg_temp
        FROM sensor_readings sr
        JOIN sensors s ON s.sensor_id = sr.sensor_id
        WHERE s.sensor_type = 'temp_c' AND sr.quality_flag = 'ok'
        GROUP BY date
    ),
    cold_days AS (
        SELECT date FROM temp_data WHERE avg_temp < 0
    ),
    warm_days AS (
        SELECT date FROM temp_data WHERE avg_temp >= 15
    )
    SELECT
        (SELECT COUNT(*) FROM citizen_requests cr JOIN cold_days cd ON substr(cr.created_ts, 1, 10) = cd.date WHERE cr.category = 'heating_issue') AS heating_cold,
        (SELECT COUNT(*) FROM citizen_requests cr JOIN warm_days wd ON substr(cr.created_ts, 1, 10) = wd.date WHERE cr.category = 'heating_issue') AS heating_warm,
        (SELECT COUNT(*) FROM cold_days) AS cold_days_cnt,
        (SELECT COUNT(*) FROM warm_days) AS warm_days_cnt;
    """
    heating_cold, heating_warm, cold_days_cnt, warm_days_cnt = conn.execute(q_cold_heating).fetchone()

    cold_rate = heating_cold / cold_days_cnt if cold_days_cnt > 0 else 0
    warm_rate = heating_warm / warm_days_cnt if warm_days_cnt > 0 else 0

    report += table_md([
        ("heating_issues_on_cold_days (<0°C)", heating_cold),
        ("heating_issues_on_warm_days (≥15°C)", heating_warm),
        ("cold_days_count", cold_days_cnt),
        ("warm_days_count", warm_days_cnt),
        ("heating_issues_per_cold_day", f"{cold_rate:.2f}"),
        ("heating_issues_per_warm_day", f"{warm_rate:.2f}"),
    ])

    if cold_rate > warm_rate * 1.5:
        report += "✅ Heating issues strongly correlated with cold weather\n\n"
    else:
        report += "⚠️ Weak correlation between cold and heating issues\n\n"

    # D: High PM2.5 -> Air quality complaints
    report += md_h("D: High PM2.5 → Air Quality Complaints", 3)
    q_pm_airq = """
    WITH pm AS (
      SELECT o.district_id AS district_id,
             substr(sr.ts, 1, 13) || ':00:00' AS hour_ts,
             AVG(sr.value) AS pm25_avg
      FROM sensor_readings sr
      JOIN sensors s ON s.sensor_id = sr.sensor_id
      JOIN city_objects o ON o.object_id = s.object_id
      WHERE s.sensor_type = 'pm25' AND sr.quality_flag='ok'
      GROUP BY o.district_id, hour_ts
    )
    SELECT 
        SUM(CASE WHEN pm.pm25_avg > 35 THEN 1 ELSE 0 END) AS hours_high_pm25,
        SUM(CASE WHEN pm.pm25_avg <= 35 THEN 1 ELSE 0 END) AS hours_normal_pm25,
        (SELECT COUNT(*) FROM citizen_requests cr 
         JOIN pm ON cr.district_id = pm.district_id 
         AND substr(cr.created_ts, 1, 13) || ':00:00' = pm.hour_ts
         WHERE cr.category = 'air_quality' AND pm.pm25_avg > 35) AS airq_high_pm,
        (SELECT COUNT(*) FROM citizen_requests cr 
         JOIN pm ON cr.district_id = pm.district_id 
         AND substr(cr.created_ts, 1, 13) || ':00:00' = pm.hour_ts
         WHERE cr.category = 'air_quality' AND pm.pm25_avg <= 35) AS airq_normal_pm
    FROM pm;
    """
    hours_high, hours_normal, airq_high, airq_normal = conn.execute(q_pm_airq).fetchone()

    high_rate = airq_high / hours_high if hours_high > 0 else 0
    normal_rate = airq_normal / hours_normal if hours_normal > 0 else 0

    report += table_md([
        ("hours_with_pm25_>35", hours_high),
        ("hours_with_pm25_≤35", hours_normal),
        ("air_quality_complaints_when_high_pm25", airq_high),
        ("air_quality_complaints_when_normal_pm25", airq_normal),
        ("complaints_per_high_pm25_hour", f"{high_rate:.4f}"),
        ("complaints_per_normal_pm25_hour", f"{normal_rate:.4f}"),
    ])

    if high_rate > normal_rate * 2:
        report += "✅ Air quality complaints strongly correlated with high PM2.5\n\n"
    else:
        report += "⚠️ Weak correlation between PM2.5 and air quality complaints\n\n"

    # E: Road condition -> Pothole complaints
    report += md_h("E: Road Condition → Pothole Complaints", 3)
    q_road_pothole = """
    SELECT co.condition,
           COUNT(DISTINCT co.object_id) AS road_cnt,
           COUNT(cr.request_id) AS pothole_cnt,
           ROUND(1.0 * COUNT(cr.request_id) / COUNT(DISTINCT co.object_id), 2) AS complaints_per_road
    FROM city_objects co
    LEFT JOIN citizen_requests cr ON cr.object_id = co.object_id AND cr.category = 'pothole'
    WHERE co.object_type = 'road_segment'
    GROUP BY co.condition
    ORDER BY 
        CASE co.condition 
            WHEN 'poor' THEN 1 
            WHEN 'fair' THEN 2 
            WHEN 'good' THEN 3 
        END;
    """
    df_road_pothole = pd.read_sql_query(q_road_pothole, conn)
    report += df_road_pothole.to_markdown(index=False) + "\n\n"

    if len(df_road_pothole) >= 2:
        poor_rate = df_road_pothole[df_road_pothole['condition'] == 'poor']['complaints_per_road'].values[
            0] if 'poor' in df_road_pothole['condition'].values else 0
        good_rate = df_road_pothole[df_road_pothole['condition'] == 'good']['complaints_per_road'].values[
            0] if 'good' in df_road_pothole['condition'].values else 0

        if poor_rate > good_rate * 2:
            report += "✅ Poor road condition strongly increases pothole complaints\n\n"
        else:
            report += "⚠️ Weak correlation between road condition and pothole complaints\n\n"

    # ===== TRANSPORT ANALYSIS =====
    report += md_h("6. Public Transport Analysis", 2)

    report += md_h("Route Punctuality (Top 10 by trips)", 3)
    q_routes = """
    SELECT route_no,
           AVG(delay_minutes) AS avg_delay,
           ROUND(100.0 * AVG(CASE WHEN delay_minutes=0 THEN 1.0 ELSE 0.0 END), 2) AS on_time_pct,
           COUNT(*) AS trips
    FROM public_transport_trips
    GROUP BY route_no
    ORDER BY trips DESC
    LIMIT 10;
    """
    df_routes = pd.read_sql_query(q_routes, conn)
    report += df_routes.to_markdown(index=False) + "\n\n"

    # Weather impact on delays
    report += md_h("Weather Impact on Delays", 3)
    q_weather = """
    SELECT weather_condition,
           AVG(delay_minutes) AS avg_delay,
           COUNT(*) AS trips
    FROM public_transport_trips
    GROUP BY weather_condition
    ORDER BY avg_delay DESC;
    """
    df_weather = pd.read_sql_query(q_weather, conn)
    report += df_weather.to_markdown(index=False) + "\n\n"

    # ===== TEMPORAL PATTERNS =====
    if cfg['generation']['days'] > 180:
        report += md_h("7. Long-Term Trends (for periods > 180 days)", 2)

        # Traffic growth over time
        report += md_h("Traffic Growth Trend", 3)
        q_traffic_trend = """
        WITH monthly AS (
            SELECT substr(sr.ts, 1, 7) AS month,
                   AVG(sr.value) AS avg_traffic
            FROM sensor_readings sr
            JOIN sensors s ON s.sensor_id = sr.sensor_id
            WHERE s.sensor_type = 'traffic_intensity' AND sr.quality_flag = 'ok'
            GROUP BY month
            ORDER BY month
        )
        SELECT month, avg_traffic,
               avg_traffic - LAG(avg_traffic) OVER (ORDER BY month) AS month_over_month_change
        FROM monthly
        LIMIT 12;
        """
        df_traffic_trend = pd.read_sql_query(q_traffic_trend, conn)
        report += df_traffic_trend.to_markdown(index=False) + "\n\n"

        # Road condition degradation
        report += md_h("Infrastructure Degradation Trend", 3)
        q_road_age = """
        WITH road_age AS (
            SELECT 
                CASE 
                    WHEN julianday('now') - julianday(install_date) < 365 THEN 'new (<1yr)'
                    WHEN julianday('now') - julianday(install_date) < 1825 THEN 'medium (1-5yr)'
                    ELSE 'old (>5yr)'
                END AS age_group,
                condition,
                COUNT(*) AS cnt
            FROM city_objects
            WHERE object_type = 'road_segment'
            GROUP BY age_group, condition
        )
        SELECT age_group, condition, cnt
        FROM road_age
        ORDER BY 
            CASE age_group 
                WHEN 'new (<1yr)' THEN 1 
                WHEN 'medium (1-5yr)' THEN 2 
                WHEN 'old (>5yr)' THEN 3 
            END,
            CASE condition 
                WHEN 'good' THEN 1 
                WHEN 'fair' THEN 2 
                WHEN 'poor' THEN 3 
            END;
        """
        df_road_age = pd.read_sql_query(q_road_age, conn)
        report += df_road_age.to_markdown(index=False) + "\n\n"

    # ===== SUMMARY STATISTICS =====
    report += md_h("8. Summary Statistics", 2)

    # Sensor readings value ranges
    report += md_h("Sensor Value Ranges", 3)
    q_sensor_ranges = """
    SELECT s.sensor_type,
           MIN(sr.value) AS min_val,
           AVG(sr.value) AS avg_val,
           MAX(sr.value) AS max_val,
           s.unit
    FROM sensor_readings sr
    JOIN sensors s ON s.sensor_id = sr.sensor_id
    WHERE sr.quality_flag = 'ok'
    GROUP BY s.sensor_type, s.unit;
    """
    df_ranges = pd.read_sql_query(q_sensor_ranges, conn)
    report += df_ranges.to_markdown(index=False) + "\n\n"

    # District summary
    report += md_h("District Summary", 3)
    q_districts = """
    SELECT d.name, d.type, d.density, d.income_level,
           d.population,
           ROUND(d.area_km2, 2) AS area_km2,
           ROUND(d.industrial_coeff, 3) AS industrial_coeff,
           COUNT(DISTINCT co.object_id) AS objects_cnt,
           COUNT(DISTINCT CASE WHEN co.object_type='road_segment' THEN co.object_id END) AS roads_cnt
    FROM districts d
    LEFT JOIN city_objects co ON co.district_id = d.district_id
    GROUP BY d.district_id, d.name, d.type, d.density, d.income_level, d.population, d.area_km2, d.industrial_coeff
    ORDER BY d.population DESC
    LIMIT 10;
    """
    df_districts = pd.read_sql_query(q_districts, conn)
    report += df_districts.to_markdown(index=False) + "\n\n"

    # Citizen requests by category
    report += md_h("Citizen Requests by Category", 3)
    q_requests = """
    SELECT category, 
           COUNT(*) AS total_requests,
           SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) AS resolved,
           ROUND(100.0 * SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) / COUNT(*), 2) AS resolution_pct,
           ROUND(AVG(CASE WHEN status='resolved' THEN resolution_hours END), 2) AS avg_resolution_hours
    FROM citizen_requests
    GROUP BY category
    ORDER BY total_requests DESC;
    """
    df_requests = pd.read_sql_query(q_requests, conn)
    report += df_requests.to_markdown(index=False) + "\n\n"

    # ===== CONTROL QUERIES =====
    report += md_h("9. Control SQL Queries", 2)
    report += """
These queries should return non-empty results if data is correctly generated:

```sql
-- Top districts by requests (last 30 days from start date)
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
       ROUND(100.0 * AVG(CASE WHEN delay_minutes=0 THEN 1.0 ELSE 0.0 END), 2) AS on_time_pct
FROM public_transport_trips
GROUP BY route_no
ORDER BY on_time_pct DESC
LIMIT 10;

-- PM2.5 high hours vs air_quality requests
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
       COUNT(DISTINCT cr.request_id) AS airq_requests
FROM pm
LEFT JOIN citizen_requests cr
  ON cr.district_id=pm.district_id
 AND substr(cr.created_ts, 1, 13) || ':00:00' = pm.hour_ts
 AND cr.category='air_quality'
GROUP BY pm.district_id
ORDER BY hours_pm25_gt_35 DESC
LIMIT 10;

-- Road network connectivity: Check if all districts are connected
WITH RECURSIVE connected_nodes AS (
    -- Start from node 1
    SELECT DISTINCT from_node_id AS node_id
    FROM city_objects
    WHERE object_type = 'road_segment' AND from_node_id = 1

    UNION

    -- Recursively add connected nodes
    SELECT DISTINCT co.to_node_id
    FROM city_objects co
    JOIN connected_nodes cn ON cn.node_id = co.from_node_id
    WHERE co.object_type = 'road_segment'

    UNION

    SELECT DISTINCT co.from_node_id
    FROM city_objects co
    JOIN connected_nodes cn ON cn.node_id = co.to_node_id
    WHERE co.object_type = 'road_segment'
)
SELECT 
    (SELECT COUNT(*) FROM road_network_nodes) AS total_nodes,
    COUNT(*) AS connected_nodes
FROM connected_nodes;

-- Road condition impact on pothole complaints
SELECT co.condition,
       COUNT(DISTINCT co.object_id) AS total_roads,
       COUNT(cr.request_id) AS pothole_complaints,
       ROUND(1.0 * COUNT(cr.request_id) / COUNT(DISTINCT co.object_id), 2) AS complaints_per_road
FROM city_objects co
LEFT JOIN citizen_requests cr ON cr.object_id = co.object_id AND cr.category = 'pothole'
WHERE co.object_type = 'road_segment'
GROUP BY co.condition
ORDER BY 
    CASE co.condition 
        WHEN 'poor' THEN 1 
        WHEN 'fair' THEN 2 
        WHEN 'good' THEN 3 
    END;

-- Road type vs average traffic intensity
SELECT co.road_type,
       COUNT(*) AS road_count,
       ROUND(AVG(sr.value), 2) AS avg_traffic_intensity,
       ROUND(AVG(co.max_speed_kmh), 2) AS avg_speed_limit
FROM city_objects co
JOIN sensors s ON s.object_id = co.object_id
JOIN sensor_readings sr ON sr.sensor_id = s.sensor_id
WHERE co.object_type = 'road_segment'
  AND s.sensor_type = 'traffic_intensity'
  AND sr.quality_flag = 'ok'
GROUP BY co.road_type
ORDER BY avg_traffic_intensity DESC;

-- Event types impact comparison
SELECT e.event_type,
       COUNT(*) AS event_count,
       ROUND(AVG(e.noise_increase_db), 2) AS avg_noise_increase,
       ROUND(AVG(e.traffic_increase_percent), 2) AS avg_traffic_increase,
       ROUND(AVG(e.expected_attendance), 0) AS avg_attendance
FROM municipal_events e
GROUP BY e.event_type
ORDER BY avg_traffic_increase DESC;

-- Meter peak times by utility type
SELECT sm.utility_type,
       SUM(CASE WHEN mr.is_peak = 1 THEN 1 ELSE 0 END) AS peak_readings,
       COUNT(*) AS total_readings,
       ROUND(100.0 * SUM(CASE WHEN mr.is_peak = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS peak_pct
FROM meter_readings mr
JOIN smart_meters sm ON sm.meter_id = mr.meter_id
GROUP BY sm.utility_type;
```

"""

    # ===== FINAL VERDICT =====
    report += md_h("10. Validation Verdict", 2)

    issues = []
    if len(fk) > 0:
        issues.append(f"❌ {len(fk)} foreign key violations")
    if objects_out > 0 or events_out > 0 or nodes_out > 0 or roads_out > 0:
        issues.append("❌ Some coordinates outside bbox")
    if bad_zero_rule > 0 or bad_suspect_rule > 0:
        issues.append(f"❌ Quality rule violations (zero_rule: {bad_zero_rule}, suspect_rule: {bad_suspect_rule})")
    if orphan_nodes > 0:
        issues.append(f"❌ {orphan_nodes} orphan nodes in road network")
    if (null_from or 0) > 0 or (null_to or 0) > 0:
        issues.append(f"❌ Road segments with null nodes (from: {null_from or 0}, to: {null_to or 0})")

    warnings = []
    if miss_share < 0.03 or miss_share > 0.07:
        warnings.append(f"⚠️ Missing data share {miss_share:.4f} outside expected range [0.03, 0.07]")
    if susp_share < 0.01 or susp_share > 0.02:
        warnings.append(f"⚠️ Suspect data share {susp_share:.4f} outside expected range [0.01, 0.02]")
    if road_pct < 25 or road_pct > 35:
        warnings.append(f"⚠️ Road segments {road_pct:.1f}% of objects, expected ~30%")

    if not issues:
        report += "### ✅ **PASSED**: Dataset is valid!\n\n"
    else:
        report += "### ❌ **FAILED**: Critical issues detected\n\n"
        for issue in issues:
            report += f"- {issue}\n"
        report += "\n"

    if warnings:
        report += "### ⚠️ Warnings:\n\n"
        for warning in warnings:
            report += f"- {warning}\n"
        report += "\n"

    if not issues and not warnings:
        report += "**No issues or warnings detected. Dataset meets all validation criteria.** 🎉\n\n"

    # Write report
    out_path.write_text(report, encoding="utf-8")
    conn.close()

    print(f"✅ Validation complete!")
    print(f"📊 Report saved to: {out_path}")

    if issues:
        print(f"\n❌ FAILED: {len(issues)} critical issue(s) detected")
        sys.exit(1)
    elif warnings:
        print(f"\n⚠️ PASSED with {len(warnings)} warning(s)")
        sys.exit(0)
    else:
        print(f"\n✅ PASSED: All validation checks successful")
        sys.exit(0)


if __name__ == "__main__":
    main()
