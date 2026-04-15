import os
from dotenv import load_dotenv

load_dotenv()

# === LLM ===
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Models
LLM_FILTER_MODEL_ANTHROPIC = "claude-haiku-4-5-20251001"
LLM_SUMMARIZE_MODEL_ANTHROPIC = "claude-sonnet-4-6"
LLM_FILTER_MODEL_OPENAI = "gpt-4o-mini"
LLM_SUMMARIZE_MODEL_OPENAI = "gpt-4o"

# === Telegram bot ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === Telegram MTProto (Telethon — for channel reading) ===
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")

# Channels to monitor (e.g. ["@sostav_ru", "@adindex_news"])
TELEGRAM_CHANNELS: list[str] = [
    ch.strip()
    for ch in os.getenv("TELEGRAM_CHANNELS", "").split(",")
    if ch.strip()
]

# === BrowserAct ===
BROWSERACT_API_KEY = os.getenv("BROWSER_ACT_API_KEY", "")
BROWSERACT_BASE_URL = "https://api.browseract.com/v2/workflow"
BROWSERACT_WORKFLOW_SOSTAV = os.getenv("BROWSERACT_WORKFLOW_SOSTAV", "")
BROWSERACT_WORKFLOW_ADINDEX = os.getenv("BROWSERACT_WORKFLOW_ADINDEX", "")
BROWSERACT_WORKFLOW_OUTDOOR = os.getenv("BROWSERACT_WORKFLOW_OUTDOOR", "")
BROWSERACT_WORKFLOW_TEXT_EXTRACT = os.getenv("BROWSERACT_WORKFLOW_TEXT_EXTRACT", "")

# === Filtering ===
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.7"))

# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# === Search queries ===
GOOGLE_NEWS_QUERIES = [
    '"Медиагруппа РИМ"',
    '"Rim Group" наружная реклама',
    '"РИМ" наружная реклама',
    'rimgroup.ru',
]

BROWSERACT_QUERIES = [
    "Медиагруппа РИМ",
    "Rim Group наружная реклама",
]

# === Industry RSS sources ===
INDUSTRY_RSS_SOURCES = {
    "Sostav": "https://sostav.ru/rss",
    "AdIndex": "https://adindex.ru/rss/",
    "RBC": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "Kommersant": "https://www.kommersant.ru/RSS/news.xml",
    "TASS": "https://tass.com/rss/v2.xml",
}

# === Keyword filter patterns (regex, case-insensitive) ===
INCLUDE_PATTERNS = [
    r"медиагрупп.{0,8}рим",  # медиагрупп(а/е/у) (+кавычки) рим — любые варианты
    r"rim\s*group",
    r"rimgroup",
    r"рим\s*груп",
    r"рим.{0,20}наружн",
    r"рим.{0,20}(ooh|outdoor|билборд)",
    r"rimgroup\.ru",
]

EXCLUDE_PATTERNS = [
    r"древн(ий|его|ему)\s+рим",
    r"рим\s*(итали|вечный\s+город)",
    r"римск(ая|ое|ий|ого)\s+(импери|прав|клуб|папа)",
    r"\broma\b",
    r"рим\s+и\s+(париж|лондон|мадрид)",
]

# === Database ===
DB_PATH = os.path.join(os.path.dirname(__file__), "news_monitor.db")
