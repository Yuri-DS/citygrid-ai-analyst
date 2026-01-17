#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from pathlib import Path

import sqlite3
import pandas as pd

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def main() -> None:
    cfg_path = Path("configs/citygrid_generation.yaml")
    if len(os.sys.argv) >= 2:
        cfg_path = Path(os.sys.argv[1])

    # минимально читаем sqlite_path из yaml без зависимости pyyaml (folium опциональный)
    import yaml
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    db_path = Path(cfg["output"]["sqlite_path"])
    out_html = Path("outputs/citygrid_map.html")
    ensure_dir(out_html.parent)

    try:
        import folium
    except Exception:
        print("folium is not installed. Install: pip install folium")
        return

    conn = sqlite3.connect(str(db_path))

    districts = pd.read_sql_query("SELECT district_id, name, center_lat, center_lon FROM districts", conn)
    objs = pd.read_sql_query("""
        SELECT object_id, district_id, object_type, name, lat, lon
        FROM city_objects
        WHERE object_type IN ('stop','parking','substation','park')
        ORDER BY object_id
        LIMIT 1500
    """, conn)
    ev = pd.read_sql_query("""
        SELECT event_id, district_id, event_type, name, start_ts, end_ts, lat, lon, impact_radius_km
        FROM municipal_events
        ORDER BY event_id
        LIMIT 600
    """, conn)

    conn.close()

    # center map
    c_lat = float(districts["center_lat"].mean())
    c_lon = float(districts["center_lon"].mean())
    m = folium.Map(location=[c_lat, c_lon], zoom_start=12, tiles="OpenStreetMap")

    # district centers
    for _, r in districts.iterrows():
        folium.CircleMarker(
            location=[float(r["center_lat"]), float(r["center_lon"])],
            radius=6,
            tooltip=f"District {int(r['district_id'])}: {r['name']}",
        ).add_to(m)

    # objects
    for _, r in objs.iterrows():
        folium.CircleMarker(
            location=[float(r["lat"]), float(r["lon"])],
            radius=2,
            tooltip=f"{r['object_type']} | {r['name']} (d={int(r['district_id'])})",
        ).add_to(m)

    # events (circle)
    for _, r in ev.iterrows():
        folium.Circle(
            location=[float(r["lat"]), float(r["lon"])],
            radius=float(r["impact_radius_km"]) * 1000.0,
            tooltip=f"event {int(r['event_id'])}: {r['event_type']} | {r['start_ts']}..{r['end_ts']}",
            fill=False,
        ).add_to(m)

    m.save(str(out_html))
    print(f"OK: saved {out_html}")

if __name__ == "__main__":
    main()
