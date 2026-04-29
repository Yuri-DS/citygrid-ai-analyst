# CityGrid - Fast Validation Report

**Note:** This is a fast validation that skips heavy aggregations.
For full validation, use `validate_dataset.py`

- DB: `D:\CityGrid AI Analyst\data\citygrid.db`
- Scale: `small`
- Period: 45 days

## 1. Basic Integrity
| Metric | Value |
|---|---|
| foreign_key_violations | 0 |

✅ No FK violations

## 2. Row Counts
- **districts**: 5
- **road_network_nodes**: 100
- **city_objects**: 500
- **sensors**: 750
- **smart_meters**: 300
- **municipal_events**: 75
- **citizen_requests**: 10,000
- **public_transport_trips**: 50,000
- **sensor_readings**: 810,000
- **meter_readings**: 324,000

## 3. Road Network
| Metric | Value |
|---|---|
| road_segments | 150 |
| road_segments_pct | 30.0% |
| orphan_nodes | 2 |

⚠️ Check road network details

## 4. Data Quality (Full Check)
| Metric | Value |
|---|---|
| total_readings | 810,000 |
| ok_count | 754,584 |
| missing_count | 43,179 |
| suspect_count | 12,237 |
| ok_share | 0.9316 |
| missing_share | 0.0533 |
| suspect_share | 0.0151 |
| avg_suspect_anomaly_score | 0.7259 |

✅ Quality flags in expected range

## 5. Causality (Simplified)
| condition   |   complaints |
|:------------|-------------:|
| fair        |          352 |
| good        |          118 |
| poor        |          738 |

✅ Poor roads → more pothole complaints

## 6. Fast Validation Verdict
### ⚠️ **ISSUES DETECTED**:

- Orphan nodes

