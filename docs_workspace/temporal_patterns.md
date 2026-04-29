# Temporal Patterns

## Daily Seasonality
- Traffic peaks: 07-10, 17-20
- Noise reduction at night
- Consumption profiles vary by utility type

## Weekly Patterns
- Weekend traffic approximately 30% lower than weekdays
- Commercial areas quieter on weekends

## Seasonal Patterns (for longer data periods)
- Seasonal heating/cooling patterns in meter_readings
- Use time-based GROUP BY to discover trends: `GROUP BY strftime('%m', ts)`
