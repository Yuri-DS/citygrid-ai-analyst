# CityGrid - KPI definitions

## Peak consumption (meter_readings.is_peak)
For each meter, is_peak = 1 when hourly consumption is above the meter's 90th percentile over the generated period.

## Punctuality / delay
Delay (minutes) = actual_ts - scheduled_ts.
Delays depend on district traffic intensity and peak hours.

## Request resolution
If status = resolved:
resolved_ts = created_ts + resolution_hours.
Resolution time depends on category and priority.
