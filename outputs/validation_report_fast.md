# CityGrid - Fast Validation Report

**Note:** This is a fast validation that skips heavy aggregations.
For full validation, use `validate_dataset.py`

- DB: `D:\CityGrid AI Analyst\data\citygrid.db`
- Scale: `medium`
- Period: 90 days

## 1. Basic Integrity
| Metric | Value |
|---|---|
| foreign_key_violations | 0 |

✅ No FK violations

## 2. Row Counts
- **districts**: 10
- **road_network_nodes**: 250
- **city_objects**: 2,000
- **sensors**: 3,000
- **smart_meters**: 1,200
- **municipal_events**: 300
- **citizen_requests**: 40,000
- **public_transport_trips**: 200,000
- **sensor_readings**: 6,480,000
- **meter_readings**: 2,592,000

## 3. Road Network
| Metric | Value |
|---|---|
| road_segments | 600 |
| road_segments_pct | 30.0% |
| orphan_nodes | 0 |

✅ Road network looks good

## 4. Data Quality (Full Check)
| Metric | Value |
|---|---|
| total_readings | 6,480,000 |
| ok_count | 5,959,503 |
| missing_count | 407,199 |
| suspect_count | 113,298 |
| ok_share | 0.9197 |
| missing_share | 0.0628 |
| suspect_share | 0.0175 |
| avg_suspect_anomaly_score | 0.7017 |

✅ Quality flags in expected range

## 5. Causality (Simplified)
| condition   |   complaints |
|:------------|-------------:|
| fair        |         1501 |
| good        |          520 |
| poor        |         3076 |

✅ Poor roads → more pothole complaints

## 6. Fast Validation Verdict
### ✅ **PASSED**: Basic validation successful

Run full validation with `validate_dataset.py` for detailed checks.
