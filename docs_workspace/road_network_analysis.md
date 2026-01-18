# Road Network Analysis

## Graph Structure
Дорожная сеть представлена графом:
- Вершины: road_network_nodes
- Рёбра: city_objects с object_type='road_segment'

## Generation Algorithm
Используется триангуляция Делоне:
1. Опорные точки: центры районов + важные объекты
2. Триангуляция создаёт рёбра
3. Назначение атрибутов по длине и типу района

## Key Metrics
- Connectivity: все районы связаны
- Avg path length: средняя длина пути
- Road condition distribution: good/fair/poor
