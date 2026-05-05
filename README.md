# CityGrid AI Analyst

Интеллектуальный AI-аналитик для городской инфраструктуры: принимает вопросы на естественном языке и возвращает аналитические ответы на основе SQL, RAG и визуализаций.

## Статус проекта

Проект завершен и готов к демонстрации как итоговое решение ВКР.

## Что умеет система

- Преобразует вопрос пользователя в план анализа и SQL-запросы.
- Выполняет безопасные SQL-запросы к городской БД (SQLite).
- Строит интерактивные графики (Plotly) и карты (Folium).
- Использует RAG-поиск по доменной документации из `docs_workspace`.
- Показывает промежуточные шаги рассуждения агента в интерфейсе.
- Работает с двумя провайдерами LLM: локальный Ollama и облачный OpenAI.

## Архитектура решения

Проект построен на модульном агенте (`LangGraph`) с набором инструментов:

- `sql_tool` - выполнение и контроль SQL-запросов;
- `plot_tool` - генерация графиков из табличных результатов;
- `map_tool` - построение карт по геоданным;
- `rag_tool` - извлечение контекста из документов.

Пользователь взаимодействует с системой через Streamlit-интерфейс (`app_agent.py`), где отображаются:

- диалог,
- ответ агента,
- визуализации,
- прогресс выполнения шагов и tool-calls.

## Технологический стек

- `Python 3.10+`
- `Streamlit`
- `LangGraph / LangChain`
- `SQLite + SQLAlchemy`
- `Plotly`
- `Folium`
- `ChromaDB` (RAG)
- `Ollama` и `OpenAI API`

## Быстрый запуск

```bash
git clone https://github.com/your-username/citygrid-ai-analyst.git
cd citygrid-ai-analyst

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
python scripts/init_rag.py
```

### Вариант 1: локальная модель через Ollama

```bash
ollama serve
ollama pull qwen2.5:7b
streamlit run app_agent.py
```

### Вариант 2: OpenAI API

1. Запустите приложение:

```bash
streamlit run app_agent.py
```

2. В Sidebar выберите `ChatGPT (OpenAI API)`.
3. Введите API-ключ и модель (например, `gpt-4o-mini`).

## Структура репозитория

```text
citygrid-ai-analyst/
├── app_agent.py                  # Основной Streamlit UI для AI-аналитика
├── app.py                        # Ранний SQL-прототип (legacy)
├── configs/
│   ├── agent_config.yaml         # Параметры LLM и поведения агента
│   └── citygrid_generation.yaml  # Настройки генерации городского датасета
├── scripts/
│   ├── init_rag.py
│   ├── citygrid_generator.py
│   ├── voronoi_citygrid_generator.py
│   └── validate_dataset.py
├── src/
│   ├── agent/
│   │   ├── graph.py
│   │   ├── prompts.py
│   │   └── tools/
│   ├── database/
│   └── rag/
└── docs_workspace/               # Документы для RAG-индекса
```

## Примеры запросов

- `How many districts are in the city?`
- `Show top 5 districts by population`
- `Plot monthly dynamics of citizen requests`
- `Build a map of districts with population density`
- `Compare sensor types by number of active devices`

## Ограничения и замечания

- Для локального режима требуется установленный и запущенный Ollama.
- Для облачного режима необходим валидный OpenAI API key.
- Полнота и точность ответа зависят от качества данных и формулировки запроса.

## Научный контекст

Проект реализован как выпускная квалификационная работа магистратуры по теме разработки AI-агента-аналитика на основе предобученных языковых моделей для задач городской аналитики.
