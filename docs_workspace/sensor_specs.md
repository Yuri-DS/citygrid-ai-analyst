# CityGrid - Sensor Specs

## noise_db
Единицы: dB
Типичные значения: 30-90
Связи: зависит от traffic_intensity, повышается во время событий

## traffic_intensity
Единицы: veh/h
Типичные значения: 20-500
Связи: пики 07-10 и 17-20, растет во время событий

## pm25
Единицы: ug/m3
Типичные значения: 5-120
Связи: растет с traffic_intensity и industrial_coeff

## temp_c
Единицы: C
Типичные значения: -30..35
Связи: влияет на heating_gcal
