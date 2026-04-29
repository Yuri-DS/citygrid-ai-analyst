# 🏙️ CityGrid AI Analyst

AI-агент для анализа городской инфраструктуры на естественном языке.

---

## 🚧 Раздел временно не ведётся до завершения базовой структуры проекта.
## ~~🚀 Ближайшие задачи~~ 


- [ ] *Изменить генерацию дорог. Генерируется слишком много Highway (ETA: 29.01.2026)*
- [ ] Добавить визуализацию по точкам

## Выполнено
- [x] Исправить генерацию районов, чтобы не были внутри друг друга. Решение через алгоритм Вороного (done: 21.01.2026)
- [x] Изменить отрисовку карты районов (done: 21.01.2026)
- [x] УДАЛИЛ (ОТЛОЖЕНО ДО ~7 ФАЗЫ) Исправить баг BUG-001 — Example Questions (ETA: 27.01.2026)
- [x] **Починить вывод ответа, графиков, карты (bug-002)**
---

## О проекте

CityGrid AI Analyst — это интеллектуальный помощник, который позволяет задавать вопросы о городских данных на естественном языке и получать ответы на основе реальных данных из базы.

**Возможности:**
- 💬 Вопросы на естественном языке → SQL запросы
- 🔍 Автоматическая валидация и безопасность SQL
- 📊 Анализ: районы, сенсоры, обращения граждан, транспорт
- 📈 Графики (Plotly) и карты (Folium)
- 📚 RAG — поиск по документации
- 🤖 Прозрачный reasoning — видно как агент думает

## Технологии

- **LLM**: Ollama (Llama 3.1, Qwen 2.5, Granite) или OpenAI (GPT-4o mini)
- **Agent Framework**: LangGraph
- **Database**: SQLite
- **RAG**: ChromaDB
- **UI**: Streamlit

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/your-username/citygrid-ai-analyst.git
cd citygrid-ai-analyst

# 2. Создать виртуальное окружение
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Векторизировать документы (RAG)
python scripts/init_rag.py

# 5. Запустить Ollama (в отдельном терминале)
ollama pull llama3.1:8b
ollama serve

# 6. Запустить приложение
streamlit run app_agent.py
```

## Структура проекта

```
citygrid-ai-analyst/
├── app_agent.py              # Streamlit приложение
├── src/
│   ├── agent/                # LangGraph агент
│   │   ├── graph.py          # Основная логика
│   │   ├── prompts.py        # Системные промпты
│   │   └── tools/            # Инструменты
│   │       ├── sql_tool.py   # SQL запросы
│   │       ├── plot_tool.py  # Графики Plotly
│   │       ├── map_tool.py   # Карты Folium
│   │       └── rag_tool.py   # RAG поиск
│   ├── database/             # Работа с БД
│   │   ├── connection.py
│   │   └── validator.py
│   └── rag/                  # Векторное хранилище
│       └── vector_store.py
├── docs_workspace/           # Документация для RAG
├── data/
│   └── citygrid.db           # База данных
├── configs/
│   ├── agent_config.yaml
│   └── citygrid_generation.yaml
└── scripts/
    ├── init_rag.py           # Инициализация RAG
    ├── citygrid_generator.py # Генерация данных
    └── validate_dataset.py   # Валидация датасета
```

## Примеры вопросов

- "How many districts are in the city?"
- "Show me top 5 districts by population"
- "How many sensors of each type are there?"
- "What is the total population of all districts?"
- "Show a map of districts with population density"
- "Plot sensor readings over time"

## Известные баги

См. [BUGS.md](BUGS.md)

## Статус

🚧 В разработке (Фаза 3 — визуализация)

## Автор

Выпускная квалификационная работа магистратуры.  
Тема: "Разработка AI-агента-аналитика на основе предобученной языковой модели"
