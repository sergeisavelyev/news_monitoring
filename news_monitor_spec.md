# Спецификация: Интеллектуальный мониторинг новостей
## «Медиагруппа РИМ» / Rim Group

**Версия:** 1.1  
**Дата:** 2026-04-15  
**Статус:** В разработке (Phase 1 завершена)  

---

## 0. Статус реализации (актуально на 2026-04-15)

### Реализовано и проверено ✅

| Компонент | Файл | Статус |
|-----------|------|--------|
| Модель данных | `models/news_item.py` | ✅ |
| SQLite хранилище | `storage/sqlite_storage.py` | ✅ |
| Хеширование + дедупликация | `processing/content_hasher.py`, `deduplicator.py` | ✅ |
| Keyword filter (regex) | `processing/keyword_filter.py` | ✅ |
| Pipeline оркестратор | `processing/pipeline.py` | ✅ |
| LLM клиент (Anthropic/OpenAI) | `ai/llm_client.py` | ✅ |
| LLM фильтр релевантности | `ai/relevance_filter.py` | ✅ |
| LLM суммаризатор | `ai/summarizer.py` | ✅ |
| Google News RSS коллектор | `collectors/google_news.py` | ✅ |
| Sostav.ru коллектор (browser-act CLI) | `collectors/sostav_collector.py` | ✅ |
| Одноразовый запуск / тест | `run_once.py` | ✅ |
| BrowserAct API тестер | `test_browseract.py` | ✅ |

### В разработке / не начато ⬜

| Компонент | Файл | Приоритет |
|-----------|------|-----------|
| Извлечение полного текста статьи | `collectors/text_extractor.py` | P1 |
| Telegram бот (уведомления) | `bot/` | P1 |
| Планировщик (APScheduler) | `scheduler/jobs.py` | P2 |
| Industry RSS коллектор | `collectors/industry_rss.py` | P2 |
| BrowserAct cloud коллектор | `collectors/browseract_collector.py` | P3 (частично) |
| Telegram каналы | `collectors/telegram_channels.py` | P3 |

### Ключевые технические решения (итоги Phase 1)

**browser-act-cli вместо облачного BrowserAct API**

Облачный BrowserAct API (`api.browseract.com`) имеет ограничение: передача
именованных параметров (`input_parameters`) в workflow работает только через
эндпоинт `run-task-by-template` (требует отдельно созданные Templates, не Workflows).
Обычный `run-task` не поддерживает динамические параметры.

Решение: **browser-act-cli** — локальный CLI-инструмент (`pip: browser-act-cli`),
который запускает stealth-браузер локально. Преимущества:
- Бесплатный (нет кредитов за запуск)
- Полный контроль над запросами и навигацией
- Anti-detection stealth режим
- Поддержка captcha solving

Установка: `uv tool install browser-act-cli --python 3.12`  
Путь на Windows: `C:\Users\admin\.local\bin\browser-act.exe`  
Браузер для Sostav: `browser_id = 90674564485747216` (тип: stealth, normal mode)

**Keyword filter: обработка кавычек**

На Sostav.ru компания называется `Медиагруппа «РИМ»` (с ёлочками).
Паттерн `медиагрупп[аеуы]\s+рим` не совпадал. Исправлено на:
```python
r"медиагрупп.{0,8}рим"  # покрывает «РИМ», "РИМ", РИМ — любые варианты
```

**Проверенные результаты (тест 2026-04-15)**

- Sostav.ru: 30 статей → 3 релевантных → LLM conf=0.95 → sentiment=positive
- Google News: 10 статей → 1 релевантная → LLM conf=0.95 → sentiment=neutral
- Дедупликация между запусками работает корректно

---

## 1. Резюме проекта

### 1.1 Цель

Автоматизированный сбор, фильтрация, AI-суммаризация и доставка новостных
упоминаний компании **«Медиагруппа РИМ»** (Rim Group) — оператора наружной
рекламы в России — через Telegram-бот с возможностью управления подпиской.

### 1.2 Проблема

Название «РИМ» — сильный омоним (город Рим, римское право, исторические
контексты). Простой текстовый поиск даёт до 90 % нерелевантных результатов.
Необходим интеллектуальный слой фильтрации.

### 1.3 Ключевые решения

- Мультиисточниковый сбор (RSS, поисковые системы, Telegram-каналы)
- Двухступенчатая фильтрация: быстрая (ключевые слова) + точная (LLM)
- AI-суммаризация и анализ тональности каждой релевантной статьи
- Telegram-бот для доставки и управления
- SQLite-хранилище для дедупликации и аналитики

---

## 2. Архитектура системы

### 2.1 Общая схема

```
┌──────────────────────────────────────────────────────────┐
│                    ИСТОЧНИКИ ДАННЫХ                      │
│                                                          │
│  Google News RSS    Отраслевые RSS    Telegram-каналы    │
│       │                  │                  │            │
│       │    BrowserAct (Sostav search,        │            │
│       │    AdIndex search, Outdoor.ru)        │            │
│       │         │                    │                   │
└───────┼─────────┼────────────────────┼───────────────────┘
        │         │                    │
        ▼         ▼                    ▼
┌──────────────────────────────────────────────────────────┐
│              КОЛЛЕКТОРЫ (Collectors)                      │
│                                                          │
│  GoogleNewsCollector   IndustryRSSCollector               │
│  TelegramCollector     BrowserActCollector                │
│  [YandexNewsCollector — BACKLOG]                         │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│         ПАЙПЛАЙН ОБРАБОТКИ (Pipeline)                    │
│                                                          │
│  1. Дедупликация (MD5-хеш заголовок + URL)               │
│  2. Быстрый фильтр (regex + ключевые слова)             │
│  3. Извлечение полного текста (web scraping)             │
│  4. LLM-фильтр релевантности (порог ≥ 0.7)             │
│  5. LLM-суммаризация + тональность                      │
│  6. Сохранение в SQLite                                  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              ДОСТАВКА (Telegram Bot)                      │
│                                                          │
│  Уведомления о новых статьях                             │
│  Команды: /latest  /stats  /search  /settings            │
│  Дайджест (ежедневный / еженедельный)                    │
└──────────────────────────────────────────────────────────┘
```

### 2.2 Компоненты

| Компонент | Назначение | Технология |
|-----------|-----------|------------|
| Collectors | Сбор сырых данных из источников | aiohttp, feedparser, Telethon |
| BrowserAct | AI-скрейпинг сайтов без RSS | BrowserAct API (облачный сервис) |
| Pipeline | Обработка, фильтрация, обогащение | Python asyncio |
| LLM Engine | Фильтрация релевантности + суммаризация | Anthropic API (Claude) или OpenAI API |
| Storage | Хранение, дедупликация, поиск | SQLite |
| Bot | Доставка уведомлений, интерфейс управления | python-telegram-bot |
| Scheduler | Периодический запуск пайплайна | APScheduler |

---

## 3. Источники данных

### 3.1 Google News RSS (бесплатно)

**Описание:** Google предоставляет RSS-ленту результатов поиска в Google News.  
**URL-шаблон:**  
```
https://news.google.com/rss/search?q={query}&hl=ru&gl=RU&ceid=RU:ru
```

**Особенности:**
- Бесплатный, без API-ключа
- Возвращает 10–20 последних результатов
- Задержка индексации: 15–60 минут
- Может блокировать при частых запросах (рекомендуется пауза 5–10 сек между запросами)
- URL в RSS ведут на Google-редирект; нужно извлекать реальный URL из параметра

**Поисковые запросы:**
```
"Медиагруппа РИМ"
"Rim Group" наружная реклама
"РИМ" outdoor advertising Russia
site:rimgroup.ru
```

### 3.2 Яндекс.Новости — BACKLOG

> ⏸ **Отложено.** Реализация отложена из-за высокой сложности и затрат на кредиты BrowserAct.
> Вернуться после стабилизации остальных источников.

**Почему сложно:**
- JS-рендеринг обязателен, официального API нет (закрыт в 2017)
- Агрессивная CAPTCHA и блокировки по IP
- Кластеризация новостей требует дополнительных кликов внутри групп
- Нет готового шаблона в BrowserAct — нужно строить workflow с нуля
- Высокий расход кредитов (~25–50 за запуск × 24 раза/день = ~1200 кредитов/день)

**Варианты реализации в будущем:**
- BrowserAct workflow (поиск по `yandex.ru/news/search?text={query}`)
- SerpAPI платный ($50/мес) — стабильный API для поисковой выдачи Яндекса

### 3.3 Отраслевые RSS-ленты (бесплатно)

Профильные издания рынка наружной рекламы:

| Издание | RSS-URL | Тематика |
|---------|---------|----------|
| Sostav.ru | `https://sostav.ru/rss` | Рекламный рынок России |
| AdIndex.ru | `https://adindex.ru/rss/` | Реклама и маркетинг |
| Outdoor.ru | BrowserAct (RSS нет) | Наружная реклама — нишевый портал |
| RBC — бизнес | `https://rssexport.rbc.ru/rbcnews/news/30/full.rss` | Деловые новости |
| Коммерсантъ | `https://www.kommersant.ru/RSS/news.xml` | Деловые новости |
| Ведомости | `https://vedomosti.ru/rss/news` | Деловые новости |
| ТАСС | `https://tass.com/rss/v2.xml` | Общие новости |

**Примечание:** RSS-ленты крупных СМИ содержат тысячи записей в день. Фильтрация по ключевым словам критически важна для снижения нагрузки на LLM.

### 3.4 Telegram-каналы (условно-бесплатно)

**Описание:** Мониторинг тематических Telegram-каналов.

**Целевые каналы (примеры, необходимо уточнить):**
- Каналы самой компании (если есть)
- Отраслевые каналы по наружной рекламе и OOH
- Каналы рекламных изданий (Sostav, AdIndex)

**Технология:** Telethon (MTProto API)  
**Требования:**
- Telegram API ID и API Hash (получить на my.telegram.org)
- Телефонный номер для авторизации
- Соблюдение rate limits Telegram API

**Альтернатива без авторизации:** Парсинг публичных каналов через `t.me/s/{channel}` (веб-превью). Ограничение: доступны только последние ~20 постов.

### 3.5 browser-act-cli — локальный AI-скрейпинг (АКТУАЛЬНЫЙ ПОДХОД)

> ⚠️ **Обновлено по итогам Phase 1.** Изначально планировался облачный BrowserAct API.
> По результатам тестирования выбран **browser-act-cli** (локальный CLI-инструмент).
> Облачный API оставлен как резервный вариант.

**Почему browser-act-cli вместо облачного API:**
- Облачный `run-task` не поддерживает динамические параметры (`input_parameters` игнорируется)
- `run-task-by-template` требует отдельно созданные Templates (другой тип объекта)
- browser-act-cli: бесплатный, полный контроль, stealth + captcha, 0 кредитов/запуск

**Установка:**
```bash
uv tool install browser-act-cli --python 3.12
browser-act auth set <BROWSER_ACT_API_KEY>
browser-act browser create "sostav-scraper" --desc "Sostav.ru news scraper"
# → browser_id: 90674564485747216
```

**Принцип работы (subprocess из Python):**
```python
# 1. Открыть страницу поиска
browser-act browser open <browser_id> "https://sostav.ru/search/?q=Медиагруппа+РИМ"
browser-act wait stable

# 2. Получить содержимое как markdown
browser-act get markdown --format json
# → JSON с полем "markdown" содержащим все статьи

# 3. Парсинг результатов regex-ом из markdown
```

**Реализация:** `collectors/sostav_collector.py`

**Облачный BrowserAct API (резервный вариант):**

Заменяет прямой веб-скрейпинг. Каждый источник — отдельный workflow, созданный
один раз в UI BrowserAct и вызываемый через REST API.

**Как работает:**
1. Workflow создаётся в UI browseract.com (описание на естественном языке)
2. При запуске — POST запрос к `https://api.browseract.com/v2/workflow/run-task`
3. Результат: поллинг `get-task-status` → `get-task`, либо webhook-доставка
4. Output: JSON с полями `title`, `url`, `date`, `snippet`

**Workflow-список:**

| # | Название | Целевой сайт | Input | Интервал |
|---|----------|-------------|-------|----------|
| W1 | Sostav Search | `sostav.ru/search?q={query}` | `query` | 60 мин |
| W2 | AdIndex Search | `adindex.ru/search/?q={query}` | `query` | 60 мин |
| W3 | Outdoor.ru News | `outdoor.ru/` (раздел новостей) | — | 120 мин |
| W4 | Article Text Extractor | любой URL статьи | `url` | по требованию |

**W4 (Article Text Extractor)** — универсальный workflow, вызывается пайплайном
на шаге «Извлечение полного текста» для любой статьи из любого источника.
Заменяет `processing/text_extractor.py`.

**API-интеграция (Python):**
```python
# Запуск задачи
POST https://api.browseract.com/v2/workflow/run-task
Authorization: Bearer {BROWSERACT_API_KEY}
{
  "workflow_id": "{workflow_id}",
  "input_parameters": ["{query}"]   # или [] для W3
}
→ {"id": "task_id", ...}

# Проверка статуса
GET https://api.browseract.com/v2/workflow/get-task-status?id={task_id}

# Получение результата
GET https://api.browseract.com/v2/workflow/get-task?id={task_id}
→ {"output": {"string": "[{\"title\":..., \"url\":...}]"}}
```

**Переменные окружения:**
```bash
BROWSERACT_API_KEY=...
BROWSERACT_WORKFLOW_SOSTAV=<workflow_id>
BROWSERACT_WORKFLOW_ADINDEX=<workflow_id>
BROWSERACT_WORKFLOW_OUTDOOR=<workflow_id>
BROWSERACT_WORKFLOW_TEXT_EXTRACT=<workflow_id>
```

---

## 4. Поисковые запросы и фильтрация

### 4.1 Стратегия запросов

Проблема омонимии слова «РИМ» решается комбинацией точных фраз и контекстных маркеров.

**Точные фразы (высокая точность):**
```
"Медиагруппа РИМ"
"Rim Group"
"rimgroup"
"РИМ Груп"
```

**Контекстные запросы (шире, но больше шума):**
```
"РИМ" наружная реклама
"РИМ" outdoor
"РИМ" OOH реклама
"РИМ" рекламные конструкции
"РИМ" билборд
```

### 4.2 Двухступенчатая фильтрация

#### Ступень 1 — Быстрый фильтр (без LLM)

Выполняется на стороне Python, не тратит токены LLM.

**Включающие паттерны** (хотя бы один должен совпасть):
```python
INCLUDE_PATTERNS = [
    r"медиагрупп[аеуы]\s+рим",        # склонения
    r"rim\s*group",
    r"rimgroup",
    r"рим\s*груп",
    r"рим.{0,20}наружн",               # «РИМ» рядом со словом «наружная»
    r"рим.{0,20}(ooh|outdoor|билборд)", # контекстные маркеры
    r"rimgroup\.ru",
]
```

**Исключающие паттерны** (статья отбрасывается, если совпадает БЕЗ включающих):
```python
EXCLUDE_PATTERNS = [
    r"древн(ий|его|ему)\s+рим",
    r"рим\s*(итали|вечный\s+город)",
    r"римск(ая|ое|ий|ого)\s+(импери|прав|клуб|папа)",
    r"\broma\b",
    r"рим\s+и\s+(париж|лондон|мадрид)",  # турпоездки
]
```

**Логика:**
```
Если совпал INCLUDE → пропускаем на ступень 2
Если совпал EXCLUDE и НЕ совпал INCLUDE → отбрасываем
Если ничего не совпало → отбрасываем
```

#### Ступень 2 — LLM-фильтр релевантности

Каждая статья, прошедшая быстрый фильтр, отправляется на проверку LLM.

**Системный промпт для LLM:**
```
Ты — аналитик медиамониторинга. Твоя задача — определить, относится ли
данная новость к компании «Медиагруппа РИМ» (Rim Group) — российскому
оператору наружной рекламы.

Компания занимается: наружная реклама, рекламные конструкции, билборды,
цифровые экраны, OOH-реклама, медиафасады, transit-реклама.

Ответь строго в JSON:
{
  "relevant": true/false,
  "confidence": 0.0-1.0,
  "reason": "краткое объяснение"
}

Примеры НЕрелевантных: новости о городе Рим, Римской империи,
римском праве, других компаниях с похожим названием.
```

**Пользовательский промпт:**
```
Заголовок: {title}
Источник: {source}
Текст: {snippet или full_text, первые 1500 символов}
```

**Порог:** `confidence >= 0.7` → статья считается релевантной.

---

## 5. AI-обработка

### 5.1 Провайдер LLM

Система поддерживает два провайдера (переключение через переменную окружения `LLM_PROVIDER`):

| Параметр | Anthropic (Claude) | OpenAI (GPT) |
|----------|-------------------|--------------|
| Модель для фильтрации | claude-haiku-4-5-20251001 | gpt-4o-mini |
| Модель для суммаризации | claude-sonnet-4-6 | gpt-4o |
| Стоимость (оценка) | ~$0.001–0.005 за статью | ~$0.001–0.005 за статью |
| Переменная окружения | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` |

**Рекомендация:** Для фильтрации релевантности использовать дешёвую модель
(Haiku / gpt-4o-mini), для суммаризации — более мощную (Sonnet / gpt-4o).
Это оптимизирует расходы: из 100 кандидатов фильтр обычно пропускает 5–15,
и только они идут на дорогую суммаризацию.

### 5.2 Суммаризация

**Системный промпт:**
```
Ты — аналитик рекламного рынка. Сделай краткое резюме новости
о компании «Медиагруппа РИМ» (Rim Group).

Ответь строго в JSON:
{
  "summary": "2-3 предложения: суть новости",
  "sentiment": "positive | neutral | negative",
  "topics": ["список тем: сделка, финансы, продукт, кадры, регулирование, ..."],
  "key_facts": ["ключевые факты и цифры из статьи"]
}
```

### 5.3 Оценка стоимости BrowserAct

**Тариф:** $13/мес = 10 000 кредитов  
**Стоимость одного запуска:** ~20 кредитов (3–4 шага × 5 кредитов/шаг)

| Workflow | Запрос | Интервал | Запусков/день | Кредитов/день |
|----------|--------|----------|---------------|---------------|
| W1 Sostav Search | "Медиагруппа РИМ" | 48 ч | 0.5 | ~10 |
| W2 AdIndex Search | "Медиагруппа РИМ" | 48 ч | 0.5 | ~10 |
| W3 Outdoor.ru | — | 48 ч | 0.5 | ~10 |
| W4 Text Extractor | 1 URL/вызов | по требованию | ~2–3 | ~50 |
| **Итого** | | | | **~80/день** |

**80 × 30 = ~2 400 кредитов/мес** — 24% от бюджета, остаток про запас.

**Правило экономии:** W4 вызывается только для статей, прошедших LLM-фильтр релевантности.
При «шумных» источниках (RSS) полный текст извлекается лишь для ~5–15% кандидатов.

### 5.4 Оценка стоимости LLM

При 5 запусках в день, ~50 кандидатов на запуск:

| Этап | Вызовов/день | Токенов/вызов | Стоимость/мес (Claude) |
|------|-------------|--------------|----------------------|
| Фильтрация (Haiku) | ~250 | ~800 | ~$2–4 |
| Суммаризация (Sonnet) | ~25 | ~2000 | ~$3–6 |
| **Итого** | | | **~$5–10/мес** |

---

## 6. Хранилище данных

### 6.1 SQLite — схема БД

```sql
CREATE TABLE news (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash  TEXT UNIQUE,          -- MD5(lower(title) + url) для дедупликации
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    source        TEXT,                 -- название источника (Sostav, RBC, ...)
    source_type   TEXT,                 -- rss | yandex | google | telegram | scrape
    published_at  TEXT,                 -- ISO 8601
    snippet       TEXT,                 -- исходный фрагмент
    full_text     TEXT,                 -- полный текст статьи
    ai_summary    TEXT,                 -- резюме от LLM
    ai_sentiment  TEXT,                 -- positive / neutral / negative
    ai_relevance  REAL,                 -- 0.0–1.0
    ai_topics     TEXT,                 -- JSON-массив тем
    ai_key_facts  TEXT,                 -- JSON-массив ключевых фактов
    created_at    TEXT DEFAULT (datetime('now')),
    notified      INTEGER DEFAULT 0     -- 1 = отправлено в Telegram
);

CREATE INDEX idx_news_hash ON news(content_hash);
CREATE INDEX idx_news_date ON news(created_at);
CREATE INDEX idx_news_notified ON news(notified);
CREATE INDEX idx_news_source ON news(source_type);
```

### 6.2 Почему SQLite

- Нулевая настройка — один файл, встроен в Python
- Достаточно для объёмов мониторинга одной компании (~100–500 записей/мес)
- Легко мигрировать на PostgreSQL при росте (SQL совместим на 95 %)
- Бэкап = копирование одного файла

### 6.3 Дедупликация

Хеш вычисляется как `MD5(lower(strip(title)) + "|" + strip(url))`.

Дополнительная защита: если URL уже есть в базе — пропускаем (даже если заголовок
немного отличается из-за разных источников).

---

## 7. Telegram-бот

### 7.1 Формат уведомления

```
📰 Новая статья о «Медиагруппа РИМ»

📌 Медиагруппа РИМ заключила контракт на размещение
цифровых экранов в московском метро

📊 Тональность: 🟢 Позитивная
📁 Источник: Sostav.ru
📅 2026-04-14

💡 Резюме:
Компания подписала соглашение с Московским метрополитеном
на установку 200 цифровых рекламных экранов. Сумма контракта
составляет 1.2 млрд рублей. Монтаж запланирован на Q3 2026.

🔗 Читать полностью
```

### 7.2 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и инструкция |
| `/latest` или `/latest N` | Последние N новостей (по умолчанию 5) |
| `/stats` | Статистика: всего статей, по источникам, по тональности |
| `/search ЗАПРОС` | Полнотекстовый поиск по базе |
| `/digest` | Сводка за последние 24 часа |
| `/sources` | Список активных источников и их статус |
| `/settings` | Настройки: частота уведомлений, порог релевантности |
| `/help` | Справка по командам |

### 7.3 Режимы уведомлений

Настраиваются через `/settings`:

| Режим | Описание |
|-------|----------|
| `realtime` | Каждая статья сразу (по умолчанию) |
| `hourly` | Дайджест раз в час (если есть новые) |
| `daily` | Ежедневный дайджест в 09:00 МСК |
| `weekly` | Еженедельный дайджест в понедельник 09:00 |

---

## 8. Планировщик задач

### 8.1 Расписание сбора

| Источник | Интервал | Обоснование |
|----------|----------|-------------|
| Google News RSS | 30 мин | Быстрая индексация, лёгкие запросы |
| Отраслевые RSS | 60 мин | Публикуют 5–20 статей/день |
| Telegram-каналы | 15 мин | Быстрый источник, лёгкие запросы |
| BrowserAct (Sostav/AdIndex search) | 2 880 мин (48 ч) | Раз в 2 дня, ~60 кредитов/мес |
| BrowserAct (Outdoor.ru) | 2 880 мин (48 ч) | Раз в 2 дня, ~30 кредитов/мес |
| Яндекс.Новости | — | **BACKLOG** |

### 8.2 Реализация

Библиотека `APScheduler` (AsyncIOScheduler) — запуск cron-задач внутри
asyncio event loop, совместим с python-telegram-bot.

---

## 9. Структура проекта

```
news_monitor/
├── .env                          # Переменные окружения (НЕ в git)  ✅ создан
├── .env.example                  # Шаблон переменных
├── .env.example                  # Шаблон переменных
├── requirements.txt              # Зависимости Python
├── README.md                     # Инструкция по установке и запуску
│
├── main.py                       # Точка входа: запуск бота + планировщика
├── config.py                     # Конфигурация: запросы, пороги, расписание
│
├── collectors/                   # Модули сбора данных
│   ├── __init__.py               ✅
│   ├── base.py                   # BaseCollector (абстрактный класс)  ✅
│   ├── google_news.py            # Google News RSS  ✅
│   ├── sostav_collector.py       # Sostav.ru через browser-act-cli  ✅ (НОВЫЙ)
│   ├── browseract_collector.py   # BrowserAct облачный API (резерв)  ✅ частично
│   ├── industry_rss.py           # Отраслевые RSS  ⬜
│   └── telegram_channels.py      # Telegram-каналы (Telethon)  ⬜
│   # yandex_news.py              # BACKLOG — Яндекс.Новости
│
├── processing/                   # Пайплайн обработки
│   ├── __init__.py               ✅
│   ├── pipeline.py               # Оркестратор пайплайна  ✅
│   ├── deduplicator.py           # Дедупликация по хешу  ✅
│   ├── keyword_filter.py         # Быстрый фильтр (regex)  ✅
│   ├── content_hasher.py         # Вычисление хешей  ✅
│   └── text_extractor.py         # Извлечение полного текста (browser-act-cli)  ⬜
│
├── ai/                           # AI-модули
│   ├── __init__.py               ✅
│   ├── llm_client.py             # Обёртка над Anthropic / OpenAI API  ✅
│   ├── relevance_filter.py       # LLM-фильтр релевантности (Haiku)  ✅
│   └── summarizer.py             # LLM-суммаризация + тональность (Sonnet)  ✅
│
├── storage/                      # Хранилище
│   ├── __init__.py               ✅
│   └── sqlite_storage.py         # SQLite: CRUD, поиск, статистика  ✅
│
├── bot/                          # Telegram-бот  ⬜
│   ├── __init__.py
│   ├── bot.py                    # Инициализация бота, хендлеры
│   ├── handlers.py               # Команды: /latest, /stats, /search, ...
│   ├── formatter.py              # Форматирование сообщений
│   └── notifier.py               # Отправка уведомлений
│
├── scheduler/                    # Планировщик  ⬜
│   ├── __init__.py
│   └── jobs.py                   # Определение cron-задач (APScheduler)
│
├── models/                       # Модели данных
│   ├── __init__.py               ✅
│   └── news_item.py              # Dataclass NewsItem  ✅
│
├── run_once.py                   # Одноразовый запуск для тестов  ✅
├── test_browseract.py            # Тестер BrowserAct API  ✅
├── debug_browseract.py           # Отладка форматов API  ✅
│
└── tests/                        # Тесты  ⬜
    ├── test_keyword_filter.py
    ├── test_deduplicator.py
    ├── test_pipeline.py
    └── fixtures/
        └── sample_articles.json
```

---

## 10. Зависимости

### 10.1 requirements.txt

```
# Telegram-бот
python-telegram-bot>=21.0

# HTTP-запросы (асинхронные)
aiohttp>=3.9

# Парсинг RSS
feedparser>=6.0

# Telegram-каналы (MTProto)
telethon>=1.36

# AI-провайдеры
anthropic>=0.40
openai>=1.50

# Планировщик задач
apscheduler>=3.10

# Переменные окружения
python-dotenv>=1.0

# BrowserAct облачный API — используется стандартный aiohttp (отдельный SDK не требуется)

# browser-act-cli — локальный браузер (устанавливается через uv, не pip)
# uv tool install browser-act-cli --python 3.12
# browser-act auth set <BROWSER_ACT_API_KEY>
```

### 10.2 Системные зависимости

- Python 3.11+
- SQLite 3 (встроен в Python)

---

## 11. Конфигурация

### 11.1 Переменные окружения (.env)

```bash
# === Telegram ===
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...       # Получить у @BotFather
TELEGRAM_CHAT_ID=-1001234567890             # ID чата для уведомлений
# Узнать chat_id: отправить сообщение боту, затем открыть
# https://api.telegram.org/bot<TOKEN>/getUpdates

# === LLM ===
LLM_PROVIDER=anthropic                      # anthropic | openai
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# === Telegram-каналы (опционально) ===
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abc123...
TELEGRAM_PHONE=+79001234567

# === BrowserAct (облачный API — резерв) ===
BROWSER_ACT_API_KEY=app-...                     # Также используется browser-act-cli auth
BROWSERACT_WORKFLOW_SOSTAV=90660051000427792    # Создан, но не используется (нет параметров)
BROWSERACT_WORKFLOW_ADINDEX=<workflow_id>       # W2: AdIndex search (не создан)
BROWSERACT_WORKFLOW_OUTDOOR=<workflow_id>       # W3: Outdoor.ru news (не создан)
BROWSERACT_WORKFLOW_TEXT_EXTRACT=<workflow_id>  # W4: Text extractor (не создан)

# === browser-act-cli (основной подход) ===
# Браузер создаётся один раз командой:
# browser-act browser create "sostav-scraper"
# → browser_id сохранить в константу BROWSER_ID в collectors/sostav_collector.py
# Текущий: BROWSERACT_BROWSER_SOSTAV=90674564485747216

# === Настройки ===
RELEVANCE_THRESHOLD=0.7                     # Порог релевантности (0.0–1.0)
NOTIFICATION_MODE=realtime                  # realtime | hourly | daily | weekly
DIGEST_HOUR=9                              # Час для дайджеста (МСК)
LOG_LEVEL=INFO
```

### 11.2 config.py — ключевые параметры

```python
# Поисковые запросы
SEARCH_QUERIES = [
    '"Медиагруппа РИМ"',
    '"Rim Group" наружная реклама',
    '"РИМ" наружная реклама',
    '"Rim Group" outdoor advertising',
    'rimgroup.ru',
]

# Отраслевые RSS
INDUSTRY_RSS_FEEDS = {
    "Sostav.ru":     "https://sostav.ru/rss",
    "AdIndex.ru":    "https://adindex.ru/rss/",
    "RBC Бизнес":    "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "Коммерсантъ":   "https://www.kommersant.ru/RSS/news.xml",
    "Ведомости":     "https://vedomosti.ru/rss/news",
}

# Telegram-каналы для мониторинга
TELEGRAM_CHANNELS = [
    # "@channel_name",  # Заполнить реальными каналами
]

# BrowserAct workflow IDs (заполнить после создания workflows)
import os
BROWSERACT_WORKFLOWS = {
    "sostav":       os.getenv("BROWSERACT_WORKFLOW_SOSTAV"),
    "adindex":      os.getenv("BROWSERACT_WORKFLOW_ADINDEX"),
    "outdoor":      os.getenv("BROWSERACT_WORKFLOW_OUTDOOR"),
    "text_extract": os.getenv("BROWSERACT_WORKFLOW_TEXT_EXTRACT"),
}

# Интервалы сбора (минуты)
SCHEDULE = {
    "google_news":          30,
    "industry_rss":         60,
    "telegram":             15,
    "browseract_search":  2880,   # W1 Sostav + W2 AdIndex (раз в 2 дня)
    "browseract_outdoor": 2880,   # W3 Outdoor.ru (раз в 2 дня)
    # "yandex_news":        60,   # BACKLOG
}

# BrowserAct — один точный запрос для W1/W2 (экономия кредитов)
# "Медиагруппа РИМ" — максимальная точность, минимальный шум
# Широкие запросы ("РИМ outdoor") добавить только при росте бюджета
BROWSERACT_SEARCH_QUERY = "Медиагруппа РИМ"
```

---

## 12. Детали реализации ключевых модулей

### 12.1 BaseCollector (collectors/base.py)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import aiohttp
import hashlib

@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    source_type: str  # rss | google | yandex | telegram | scrape
    published_at: Optional[str] = None
    snippet: str = ""
    full_text: str = ""
    ai_summary: str = ""
    ai_sentiment: str = ""
    ai_relevance: float = 0.0
    ai_topics: list = None
    ai_key_facts: list = None
    content_hash: str = ""

    def compute_hash(self) -> str:
        raw = f"{self.title.lower().strip()}|{self.url.strip()}"
        self.content_hash = hashlib.md5(raw.encode()).hexdigest()
        return self.content_hash


class BaseCollector(ABC):
    """Базовый класс для всех сборщиков."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
            )
        }

    @abstractmethod
    async def collect(self) -> list[NewsItem]:
        """Собрать новости из источника."""
        ...

    async def fetch_page(self, url: str) -> str:
        """Загрузить HTML-страницу с обработкой ошибок."""
        try:
            async with self.session.get(
                url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                return ""
        except Exception as e:
            logger.warning(f"Ошибка загрузки {url}: {e}")
            return ""
```

### 12.2 GoogleNewsCollector (collectors/google_news.py)

```python
import feedparser
from urllib.parse import quote_plus, urlparse, parse_qs

class GoogleNewsCollector(BaseCollector):
    BASE = "https://news.google.com/rss/search?q={q}&hl=ru&gl=RU&ceid=RU:ru"

    async def collect(self) -> list[NewsItem]:
        items = []
        for query in SEARCH_QUERIES:
            url = self.BASE.format(q=quote_plus(query))
            html = await self.fetch_page(url)
            if not html:
                continue

            feed = feedparser.parse(html)
            for entry in feed.entries:
                real_url = self._extract_real_url(entry.link)
                item = NewsItem(
                    title=entry.get("title", ""),
                    url=real_url,
                    source=entry.get("source", {}).get("title", "Google News"),
                    source_type="google",
                    published_at=entry.get("published", ""),
                    snippet=entry.get("summary", ""),
                )
                item.compute_hash()
                items.append(item)

            await asyncio.sleep(5)  # Пауза между запросами

        return items

    @staticmethod
    def _extract_real_url(google_url: str) -> str:
        """Google News RSS оборачивает ссылки в редирект."""
        parsed = urlparse(google_url)
        params = parse_qs(parsed.query)
        return params.get("url", [google_url])[0]
```

### 12.3 BrowserActCollector (collectors/browseract_collector.py)

```python
import asyncio
import json
import os
import aiohttp

BROWSERACT_BASE = "https://api.browseract.com/v2/workflow"
POLL_INTERVAL = 5   # секунд между проверками статуса
POLL_TIMEOUT  = 120 # максимум ожидания (секунды)

class BrowserActClient:
    """Обёртка над BrowserAct REST API."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.api_key = os.getenv("BROWSERACT_API_KEY")
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def run_task(self, workflow_id: str, params: list) -> str:
        """Запустить задачу, вернуть task_id."""
        async with self.session.post(
            f"{BROWSERACT_BASE}/run-task",
            headers=self.headers,
            json={"workflow_id": workflow_id, "input_parameters": params},
        ) as resp:
            data = await resp.json()
            return data["id"]

    async def wait_for_result(self, task_id: str) -> list[dict]:
        """Поллингом дождаться завершения и вернуть распарсенный JSON."""
        deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT
        while asyncio.get_event_loop().time() < deadline:
            async with self.session.get(
                f"{BROWSERACT_BASE}/get-task-status",
                headers=self.headers,
                params={"id": task_id},
            ) as resp:
                status_data = await resp.json()

            if status_data.get("status") == "completed":
                async with self.session.get(
                    f"{BROWSERACT_BASE}/get-task",
                    headers=self.headers,
                    params={"id": task_id},
                ) as resp:
                    result = await resp.json()
                raw = result.get("output", {}).get("string", "[]")
                return json.loads(raw)

            await asyncio.sleep(POLL_INTERVAL)

        raise TimeoutError(f"BrowserAct task {task_id} не завершился за {POLL_TIMEOUT}с")


class BrowserActCollector(BaseCollector):
    """Коллектор для источников через BrowserAct (Sostav, AdIndex, Outdoor.ru)."""

    def __init__(self, session: aiohttp.ClientSession, workflow_id: str,
                 source_name: str, source_type: str = "browseract"):
        super().__init__(session)
        self.client = BrowserActClient(session)
        self.workflow_id = workflow_id
        self.source_name = source_name
        self.source_type = source_type

    async def collect(self, queries: list[str] = None) -> list[NewsItem]:
        items = []
        params = queries if queries else []  # W3 Outdoor.ru — без параметров
        for query in (params or [None]):
            input_params = [query] if query else []
            try:
                task_id = await self.client.run_task(self.workflow_id, input_params)
                results = await self.client.wait_for_result(task_id)
            except Exception as e:
                logger.warning(f"BrowserAct [{self.source_name}] ошибка: {e}")
                continue

            for row in results:
                item = NewsItem(
                    title=row.get("title", ""),
                    url=row.get("url", ""),
                    source=self.source_name,
                    source_type=self.source_type,
                    published_at=row.get("date", ""),
                    snippet=row.get("snippet", ""),
                )
                item.compute_hash()
                items.append(item)

        return items
```

### 12.4 LLM-клиент (ai/llm_client.py)

```python
import os
import json

class LLMClient:
    """Унифицированная обёртка для Anthropic и OpenAI."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic")

        if self.provider == "anthropic":
            from anthropic import Anthropic
            self.client = Anthropic()
        else:
            from openai import OpenAI
            self.client = OpenAI()

    async def ask_json(
        self,
        system: str,
        user: str,
        model: str = None,
        max_tokens: int = 1024,
    ) -> dict:
        """Отправить запрос и распарсить JSON-ответ."""
        if self.provider == "anthropic":
            model = model or "claude-haiku-4-5-20251001"
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = response.content[0].text
        else:
            model = model or "gpt-4o-mini"
            response = self.client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = response.choices[0].message.content

        # Парсинг JSON из ответа LLM
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
```

### 12.4 Пайплайн обработки (processing/pipeline.py)

```python
class NewsPipeline:
    """Оркестратор: сбор → фильтрация → обогащение → сохранение → уведомление."""

    def __init__(self, storage, llm_client, notifier, collectors):
        self.storage = storage
        self.llm = llm_client
        self.notifier = notifier
        self.collectors = collectors
        self.keyword_filter = KeywordFilter()  # быстрый фильтр

    async def run(self):
        """Полный цикл обработки."""

        # 1. Сбор из всех источников
        raw_items = []
        for collector in self.collectors:
            try:
                items = await collector.collect()
                raw_items.extend(items)
                logger.info(f"{collector.__class__.__name__}: {len(items)} шт.")
            except Exception as e:
                logger.error(f"Ошибка {collector.__class__.__name__}: {e}")

        # 2. Дедупликация
        unique = [
            item for item in raw_items
            if not self.storage.exists(item.content_hash)
        ]
        logger.info(f"После дедупликации: {len(unique)} из {len(raw_items)}")

        # 3. Быстрый фильтр (ключевые слова)
        candidates = [
            item for item in unique
            if self.keyword_filter.passes(item)
        ]
        logger.info(f"После быстрого фильтра: {len(candidates)}")

        # 4. Извлечение полного текста (для тех, у кого только snippet)
        for item in candidates:
            if not item.full_text and item.url:
                item.full_text = await self._extract_text(item.url)

        # 5. LLM-фильтр релевантности
        relevant = []
        for item in candidates:
            try:
                result = await self.llm.check_relevance(item)
                if result["confidence"] >= RELEVANCE_THRESHOLD:
                    item.ai_relevance = result["confidence"]
                    relevant.append(item)
            except Exception as e:
                logger.warning(f"LLM-фильтр ошибка: {e}")

        logger.info(f"Релевантных: {len(relevant)}")

        # 6. AI-суммаризация
        for item in relevant:
            try:
                summary = await self.llm.summarize(item)
                item.ai_summary = summary.get("summary", "")
                item.ai_sentiment = summary.get("sentiment", "neutral")
                item.ai_topics = summary.get("topics", [])
                item.ai_key_facts = summary.get("key_facts", [])
            except Exception as e:
                logger.warning(f"Суммаризация ошибка: {e}")

        # 7. Сохранение + уведомление
        for item in relevant:
            is_new = self.storage.save(item)
            if is_new:
                await self.notifier.send(item)

        return len(relevant)
```

### 12.5 Telegram-бот (bot/handlers.py)

```python
from telegram import Update
from telegram.ext import ContextTypes

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот мониторинга новостей о «Медиагруппа РИМ».\n\n"
        "Команды:\n"
        "/latest — последние новости\n"
        "/stats — статистика\n"
        "/search ЗАПРОС — поиск в базе\n"
        "/digest — сводка за сутки\n"
        "/help — справка"
    )

async def cmd_latest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    limit = 5
    if ctx.args:
        try:
            limit = int(ctx.args[0])
        except ValueError:
            pass

    news = storage.get_recent(limit=min(limit, 20))
    if not news:
        await update.message.reply_text("Пока новостей нет.")
        return

    for item in news:
        msg = format_news_message(item)
        await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = storage.get_stats()
    breakdown = storage.get_sentiment_breakdown()

    text = (
        f"📊 <b>Статистика мониторинга</b>\n\n"
        f"Всего статей: {stats['total_news']}\n"
        f"Уникальных источников: {stats['unique_sources']}\n\n"
        f"🟢 Позитивных: {breakdown.get('positive', 0)}\n"
        f"⚪ Нейтральных: {breakdown.get('neutral', 0)}\n"
        f"🔴 Негативных: {breakdown.get('negative', 0)}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Использование: /search ЗАПРОС")
        return

    query = " ".join(ctx.args)
    results = storage.search(query, limit=5)

    if not results:
        await update.message.reply_text(f'Ничего не найдено по "{query}".')
        return

    for item in results:
        msg = format_news_message(item)
        await update.message.reply_text(msg, parse_mode="HTML")
```

### 12.6 Точка входа (main.py)

```python
import asyncio
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

async def main():
    # Инициализация компонентов
    storage = NewsStorage()
    llm = LLMClient()
    bot_app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    notifier = TelegramNotifier(bot_app.bot, os.getenv("TELEGRAM_CHAT_ID"))

    # Регистрация команд
    bot_app.add_handler(CommandHandler("start", cmd_start))
    bot_app.add_handler(CommandHandler("latest", cmd_latest))
    bot_app.add_handler(CommandHandler("stats", cmd_stats))
    bot_app.add_handler(CommandHandler("search", cmd_search))
    bot_app.add_handler(CommandHandler("digest", cmd_digest))
    bot_app.add_handler(CommandHandler("help", cmd_help))

    # Создание коллекторов
    session = aiohttp.ClientSession()
    collectors = [
        GoogleNewsCollector(session),
        IndustryRSSCollector(session),
        # YandexNewsCollector(session),   # раскомментировать при настройке прокси
        # TelegramCollector(session),     # раскомментировать при настройке Telethon
    ]

    pipeline = NewsPipeline(storage, llm, notifier, collectors)

    # Планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(pipeline.run, "interval", minutes=30, id="main_pipeline")
    scheduler.start()

    # Запуск бота
    await bot_app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 13. Развёртывание

### 13.1 Локальный запуск (разработка)

```bash
# 1. Клонировать репозиторий
git clone <repo_url> && cd news_monitor

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить переменные окружения
cp .env.example .env
# Заполнить .env реальными ключами

# 5. Запустить
python main.py
```

### 13.2 Серверное развёртывание

**Рекомендация:** VPS (Timeweb, Selectel, Hetzner) — $5–10/мес.

```bash
# Systemd-сервис
sudo cat > /etc/systemd/system/news-monitor.service << EOF
[Unit]
Description=News Monitor Bot
After=network.target

[Service]
User=monitor
WorkingDirectory=/opt/news_monitor
ExecStart=/opt/news_monitor/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/news_monitor/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable news-monitor
sudo systemctl start news-monitor
```

### 13.3 Docker (альтернатива)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t news-monitor .
docker run -d --env-file .env --name news-monitor \
    -v ./data:/app/data \
    news-monitor
```

---

## 14. Мониторинг и обслуживание

### 14.1 Логирование

- Все компоненты пишут в stdout (systemd/Docker подхватят)
- Уровни: INFO (штатная работа), WARNING (ошибки сбора), ERROR (критические сбои)
- Рекомендация: подключить Sentry для алертов о критических ошибках

### 14.2 Метрики для отслеживания

| Метрика | Норма | Алерт |
|---------|-------|-------|
| Новых кандидатов / цикл | 5–50 | < 1 (источник сломался) |
| Релевантных / цикл | 0–10 | > 30 (фильтр сломался) |
| Время цикла | 30–120 сек | > 300 сек |
| Ошибки LLM / цикл | 0 | > 5 |

### 14.3 Бэкапы

```bash
# Ежедневный бэкап SQLite (добавить в cron)
0 3 * * * cp /opt/news_monitor/news_monitor.db \
    /backups/news_monitor_$(date +\%Y\%m\%d).db
```

---

## 15. Возможные расширения

| Функция | Сложность | Описание |
|---------|-----------|----------|
| Мониторинг конкурентов | Средняя | Добавить запросы по Gallery, Russ Outdoor, «Восток-Медиа» |
| Веб-дашборд | Средняя | Streamlit / Grafana для визуализации трендов |
| Email-дайджест | Низкая | Еженедельная рассылка для руководства |
| Анализ трендов | Высокая | NLP-кластеризация тем, графики динамики упоминаний |
| Мультиязычный поиск | Средняя | Добавить англоязычные источники (Reuters, Campaign) |
| RAG-агент | Высокая | Вопрос-ответ по накопленной базе знаний о компании |
| Webhooks | Низкая | Интеграция со Slack, Discord, MS Teams |

---

## 16. Оценка рисков

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Блокировка парсинга Яндекса | Высокая | Среднее | Прокси, ротация UA, SerpAPI как fallback |
| Изменение вёрстки источников | Средняя | Среднее | Мониторинг ошибок, быстрые фиксы, RSS как основа |
| Ложные срабатывания (город Рим) | Средняя | Низкое | Двухступенчатый фильтр, порог 0.7 |
| Рост стоимости LLM API | Низкая | Низкое | Лимиты, дешёвые модели для фильтрации |
| Telegram-бот заблокирован | Низкая | Высокое | Бэкап-бот, Email-канал как альтернатива |

---

## 17. Оценка сроков и бюджета

### 17.1 Сроки разработки

| Этап | Срок |
|------|------|
| MVP (Google RSS + LLM + бот) | 3–5 дней |
| Добавление остальных источников | 3–5 дней |
| Тестирование и отладка | 2–3 дня |
| Развёртывание на сервере | 1 день |
| **Итого до продакшена** | **~2 недели** |

### 17.2 Ежемесячные расходы

| Статья | Стоимость |
|--------|----------|
| VPS (сервер) | $5–10 |
| LLM API (Claude / OpenAI) | $5–10 |
| SerpAPI (опционально) | $0–50 |
| **Итого** | **$10–70/мес** |

---

## Приложение A: Глоссарий

| Термин | Определение |
|--------|-------------|
| OOH | Out-of-Home — наружная реклама |
| RSS | Really Simple Syndication — формат подписки на обновления |
| LLM | Large Language Model — большая языковая модель |
| MTProto | Протокол Telegram для работы с API |
| Дедупликация | Удаление дублирующихся записей |
| Тональность | Эмоциональная окраска текста (позитивная / нейтральная / негативная) |
