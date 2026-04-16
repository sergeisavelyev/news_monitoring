"""
AdIndex.ru collector using browser-act CLI (local stealth browser).

Searches adindex.ru for a query, extracts articles from search results.
"""
import re
import json
import logging
import subprocess
import shutil
from datetime import datetime
from urllib.parse import quote

from collectors.base import BaseCollector
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

ADINDEX_SEARCH = "https://adindex.ru/search/?q={query}&page={page}"
MAX_PAGES = 2
SOURCE = "AdIndex"

_MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# Article URL must contain a year segment (/20XX/) or .phtml
ARTICLE_RE_HEADING = re.compile(
    r"#{1,4}\s*\[([^\]]+)\]\((https?://adindex\.ru[^)]+)\)[^\n]*\n"
    r"(?:[^\n]*\n){0,2}"
    r"[^\n]*?(\d{1,2})\s+([а-яё]+)\s+(\d{4})",
    re.MULTILINE | re.IGNORECASE,
)

ARTICLE_RE_PLAIN = re.compile(
    r"\[([^\]]{10,200})\]\((https?://adindex\.ru/(?:news|publication)/[^)]*(?:/20\d{2}/|\.phtml)[^)]*)\)",
    re.MULTILINE,
)


def _find_browser_act() -> str:
    candidates = [
        shutil.which("browser-act"),
        r"C:\Users\admin\.local\bin\browser-act.exe",
        r"C:\Users\admin\.local\bin\browser-act",
    ]
    for c in candidates:
        if c and shutil.os.path.isfile(c):
            return c
    raise FileNotFoundError("browser-act not found")


def _ba_json(args: list[str], timeout: int = 30) -> dict | None:
    """Run browser-act command that returns JSON output."""
    exe = _find_browser_act()
    cmd = [exe] + args + ["--format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8")
        if result.returncode != 0:
            logger.warning("browser-act error: %s", result.stderr[:300])
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.debug("browser-act %s: %s", args[0], e)
        return None


def _ba(args: list[str], timeout: int = 30) -> bool:
    """Run browser-act command that does NOT return JSON (navigate, scroll, wait, eval)."""
    exe = _find_browser_act()
    cmd = [exe] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.debug("browser-act timeout: %s", " ".join(args[:3]))
        return False
    except Exception as e:
        logger.debug("browser-act exception: %s", e)
        return False


def _extract_articles_via_eval() -> list[dict]:
    """
    Extract article links directly from DOM via JavaScript.
    Targets URLs with year path (/20XX/) or .phtml — actual articles, not nav.
    Returns list of {title, url}.
    """
    exe = _find_browser_act()
    # Match article URLs: /news/category/2024/... or /publication/category/2024/... or .phtml
    js = (
        "JSON.stringify("
        "Array.from(document.querySelectorAll('a[href]'))"
        ".filter(a => (/\\/news\\/[^/]+\\/20\\d{2}\\//.test(a.href) || "
        "             /\\/publication\\/[^/]+\\/20\\d{2}\\//.test(a.href) || "
        "             (/\\.phtml$/.test(a.href) && /adindex\\.ru/.test(a.href) && /\\/20\\d{2}\\//.test(a.href))))"
        ".map(a => ({title: a.innerText.trim().slice(0,200), url: a.href}))"
        ".filter(x => x.title.length > 15)"
        ".slice(0, 50)"
        ")"
    )
    cmd = [exe, "eval", js]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8")
        if r.returncode == 0 and r.stdout.strip():
            raw = r.stdout.strip()
            data = json.loads(raw)
            logger.info("  AdIndex eval: %d article links in DOM", len(data))
            return data
    except Exception as e:
        logger.debug("AdIndex eval extract failed: %s", e)
    return []


def _wait_for_articles(timeout_s: int = 15) -> list[dict]:
    """Poll via eval until article links appear in DOM or timeout."""
    import time
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        articles = _extract_articles_via_eval()
        if articles:
            return articles
        time.sleep(1.5)
    return []


def _parse_date_ru(day: str, month_ru: str, year: str) -> str | None:
    month_num = _MONTHS_RU.get(month_ru.lower())
    if not month_num:
        return None
    try:
        return datetime(int(year), month_num, int(day)).isoformat()
    except ValueError:
        return None


def _parse_articles(markdown: str) -> list[dict]:
    seen_urls: set[str] = set()
    articles: list[dict] = []

    for m in ARTICLE_RE_HEADING.finditer(markdown):
        title, url = m.group(1).strip(), m.group(2).strip()
        date_iso = _parse_date_ru(m.group(3), m.group(4), m.group(5))
        if url not in seen_urls:
            seen_urls.add(url)
            articles.append({"title": title, "url": url, "date": date_iso})

    for m in ARTICLE_RE_PLAIN.finditer(markdown):
        title, url = m.group(1).strip(), m.group(2).strip()
        if url in seen_urls:
            continue
        if any(skip in url for skip in ["/search", "?page=", "/tag/", "/author/"]):
            continue
        seen_urls.add(url)
        articles.append({"title": title, "url": url, "date": None})

    return articles


class AdIndexCollector(BaseCollector):
    """Collect news from adindex.ru via browser-act-cli search."""

    def __init__(self, queries: list[str] = None, browser_id: str = None):
        self.queries = queries or ["Медиагруппа РИМ"]
        from collectors.sostav_collector import BROWSER_ID as DEFAULT_BROWSER_ID
        self.browser_id = browser_id or DEFAULT_BROWSER_ID

    async def collect(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen_urls: set[str] = set()

        for query in self.queries:
            for page in range(1, MAX_PAGES + 1):
                url = ADINDEX_SEARCH.format(query=quote(query), page=page)
                logger.info("AdIndex scraping page %d: %r", page, query)

                # Open page in stealth browser
                _ba_json(["browser", "open", self.browser_id, url], timeout=90)

                # Wait for initial page load
                _ba(["wait", "stable", "--timeout", "15000"], timeout=25)

                # Scroll 1500px to trigger lazy-loaded content
                _ba(["scroll", "down", "--amount", "1500"], timeout=10)

                # PRIMARY: extract articles directly from DOM via eval
                eval_articles = _wait_for_articles(timeout_s=15)

                if eval_articles:
                    articles = [
                        {"title": a["title"], "url": a["url"], "date": None}
                        for a in eval_articles
                        if not any(skip in a["url"] for skip in
                                   ["/search", "?page=", "/tag/", "/author/", "/afisha/",
                                    "/events/", "/ratings/", "/catalogue/", "/contacts"])
                    ]
                    logger.info("  AdIndex eval found %d articles on page %d",
                                len(articles), page)
                else:
                    # FALLBACK: parse markdown
                    logger.info("  AdIndex eval found 0 links — trying markdown fallback")
                    r = _ba_json(["get", "markdown"], timeout=30)
                    if not r:
                        logger.warning("No markdown for AdIndex page %d", page)
                        break
                    markdown = r.get("markdown", "")
                    articles = _parse_articles(markdown)
                    logger.info("  AdIndex markdown parsed %d articles on page %d",
                                len(articles), page)

                if not articles:
                    logger.info("  No results on page %d — stopping (query=%r)", page, query)
                    break

                for a in articles:
                    if a["url"] in seen_urls:
                        continue
                    seen_urls.add(a["url"])
                    items.append(NewsItem(
                        title=a["title"],
                        url=a["url"],
                        source=SOURCE,
                        source_type="browseract",
                        published_at=a["date"],
                    ))

        logger.info("AdIndex collected %d total items", len(items))
        _ba_json(["session", "close", "--all"], timeout=10)
        return items
