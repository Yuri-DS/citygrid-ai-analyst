#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast validation for large datasets - skips heavy queries
"""

from __future__ import annotations

import os
import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Tuple
import datetime

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


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent

    cfg_path = project_dir / "configs" / "citygrid_generation.yaml"
    if len(os.sys.argv) >= 2:
        cfg_path = Path(os.sys.argv[1]).resolve()

    log("Loading config...")
    cfg = load_config(cfg_path)

    db_path = Path(cfg["output"]["sqlite_path"])
    if not db_path.is_absolute():
        db_path = (project_dir / db_path).resolve()

    out_path = (project_dir / "outputs" / "validation_report_fast.md").resolve()
    ensure_dir(out_path.parent)

    log("Connecting to database...")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -200000;")

    report = ""
    report += "# CityGrid - Fast Validation Report\n\n"
    report += f"**Note:** This is a fast validation that skips heavy aggregations.\n"
    report += f"For full validation, use `validate_dataset.py`\n\n"
    report += f"- DB: `{db_path}`\n"
    report += f"- Scale: `{cfg['generation']['scale']}`\n"
    report += f"- Period: {cfg['generation']['days']} days\n\n"

    # === BASIC CHECKS ===
    log("Running basic integrity checks...")
    report += md_h("1. Basic Integrity", 2)

    # Foreign keys
    fk = conn.execute("PRAGMA foreign_key_check;").fetchall()
    report += table_md([("foreign_key_violations", len(fk))])

    if len(fk) == 0:
        report += "✅ No FK violations\n\n"
    else:
        report += f"❌ {len(fk)} FK violations!\n\n"

    # === ROW COUNTS ===
    log("Counting rows...")
    report += md_h("2. Row Counts", 2)

    tables = [
        "districts", "road_network_nodes", "city_objects", "sensors",
        "smart_meters", "municipal_events", "citizen_requests",
        "public_transport_trips", "sensor_readings", "meter_readings",
    ]

    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        report += f"- **{t}**: {n:,}\n"
    report += "\n"

    # === ROAD NETWORK ===
    log("Checking road network...")
    report += md_h("3. Road Network", 2)

    road_count = conn.execute("SELECT COUNT(*) FROM city_objects WHERE object_type='road_segment'").fetchone()[0]
    total_objs = conn.execute("SELECT COUNT(*) FROM city_objects").fetchone()[0]
    road_pct = (road_count / total_objs * 100) if total_objs > 0 else 0

    orphan_nodes = conn.execute("""
        SELECT COUNT(DISTINCT rn.node_id)
        FROM road_network_nodes rn
        WHERE NOT EXISTS (
            SELECT 1 FROM city_objects co 
            WHERE co.object_type = 'road_segment' 
            AND (co.from_node_id = rn.node_id OR co.to_node_id = rn.node_id)
        );
    """).fetchone()[0]

    report += table_md([
        ("road_segments", f"{road_count:,}"),
        ("road_segments_pct", f"{road_pct:.1f}%"),
        ("orphan_nodes", orphan_nodes),
    ])

    if orphan_nodes == 0 and 25 <= road_pct <= 35:
        report += "✅ Road network looks good\n\n"
    else:
        report += "⚠️ Check road network details\n\n"

    # === QUALITY ===
    log("Checking data quality...")
    report += md_h("4. Data Quality (Full Check)", 2)

    # Check FULL dataset quality (not sample) - this is fast enough
    q = """
    SELECT
      SUM(CASE WHEN quality_flag='missing' THEN 1 ELSE 0 END) AS n_missing,
      SUM(CASE WHEN quality_flag='suspect' THEN 1 ELSE 0 END) AS n_suspect,
      SUM(CASE WHEN quality_flag='ok' THEN 1 ELSE 0 END) AS n_ok,
      COUNT(*) AS n_total,
      AVG(CASE WHEN quality_flag='suspect' THEN anomaly_score END) AS avg_suspect_score
    FROM sensor_readings;
    """
    n_missing, n_suspect, n_ok, n_total, avg_suspect_score = conn.execute(q).fetchone()

    miss_share = (n_missing / n_total) if n_total else 0.0
    susp_share = (n_suspect / n_total) if n_total else 0.0
    ok_share = (n_ok / n_total) if n_total else 0.0

    # Handle None values
    n_missing = n_missing or 0
    n_suspect = n_suspect or 0
    n_ok = n_ok or 0
    avg_suspect_score = avg_suspect_score or 0.0

    report += table_md([
        ("total_readings", f"{n_total:,}"),
        ("ok_count", f"{n_ok:,}"),
        ("missing_count", f"{n_missing:,}"),
        ("suspect_count", f"{n_suspect:,}"),
        ("ok_share", f"{ok_share:.4f}"),
        ("missing_share", f"{miss_share:.4f}"),
        ("suspect_share", f"{susp_share:.4f}"),
        ("avg_suspect_anomaly_score", f"{avg_suspect_score:.4f}"),
    ])

    if 0.03 <= miss_share <= 0.07 and 0.01 <= susp_share <= 0.02:
        report += "✅ Quality flags in expected range\n\n"
    else:
        report += f"⚠️ Quality flags outside expected range (missing: 3-7%, suspect: 1-2%)\n\n"

    # === SIMPLE CAUSALITY CHECK ===
    log("Quick causality check...")
    report += md_h("5. Causality (Simplified)", 2)

    # Just check if pothole complaints exist on poor roads
    q = """
    SELECT co.condition, COUNT(cr.request_id) AS complaints
    FROM city_objects co
    LEFT JOIN citizen_requests cr ON cr.object_id = co.object_id AND cr.category = 'pothole'
    WHERE co.object_type = 'road_segment'
    GROUP BY co.condition;
    """
    df = pd.read_sql_query(q, conn)
    report += df.to_markdown(index=False) + "\n\n"

    if 'poor' in df['condition'].values:
        poor_complaints = df[df['condition'] == 'poor']['complaints'].values[0]
        good_complaints = df[df['condition'] == 'good']['complaints'].values[0] if 'good' in df[
            'condition'].values else 0

        if poor_complaints > good_complaints:
            report += "✅ Poor roads → more pothole complaints\n\n"
        else:
            report += "⚠️ Weak road-complaint correlation\n\n"

    # === VERDICT ===
    log("Generating verdict...")
    report += md_h("6. Fast Validation Verdict", 2)

    issues = []
    if len(fk) > 0:
        issues.append("FK violations")
    if orphan_nodes > 0:
        issues.append("Orphan nodes")
    if road_pct < 25 or road_pct > 35:
        issues.append("Road segment % unusual")

    if not issues:
        report += "### ✅ **PASSED**: Basic validation successful\n\n"
        report += "Run full validation with `validate_dataset.py` for detailed checks.\n"
    else:
        report += "### ⚠️ **ISSUES DETECTED**:\n\n"
        for issue in issues:
            report += f"- {issue}\n"
        report += "\n"

    # Write report
    out_path.write_text(report, encoding="utf-8")
    conn.close()

    log(f"✅ Fast validation complete! Report: {out_path}")

    if issues:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()