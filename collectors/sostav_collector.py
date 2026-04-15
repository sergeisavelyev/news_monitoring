"""
Sostav.ru collector using browser-act CLI (local stealth browser).

Searches sostav.ru for a query, extracts articles from search results (all pages).
No cloud credits — runs locally via browser-act-cli.
"""
import re
import logging
from datetime import datetime
from urllib.parse import quote

from collectors.base import BaseCollector
from collectors.browser_act_utils import ba, ba_get_markdown, DEFAULT_BROWSER_ID
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)

BROWSER_ID = DEFAULT_BROWSER_ID
SOSTAV_SEARCH = "https://www.sostav.ru/search/?q={query}&page={page}"
MAX_PAGES = 2
SOURCE = "Sostav"

# Regex to extract articles from markdown:
# Pattern: date line then [title](url)
# e.g.  "19.12.2023\n[Медиагруппа «РИМ»...](https://...)"
ARTICLE_RE = re.compile(
    r"(\d{2}\.\d{2}\.\d{4})\s*\n\[([^\]]+)\]\((https?://[^)]+)\)",
    re.MULTILINE,
)



def _parse_articles(markdown: str) -> list[dict]:
    """Extract articles from Sostav search results markdown."""
    articles = []
    for m in ARTICLE_RE.finditer(markdown):
        date_str, title, url = m.group(1), m.group(2), m.group(3)
        # Skip navigation links and non-article URLs
        if "/search" in url or "/news/" in url.split("sostav.ru")[1][:6]:
            continue
        articles.append({
            "title": title.strip(),
            "url": url.strip(),
            "date": date_str,
        })
    return articles


def _parse_date(date_str: str) -> str | None:
    try:
        return datetime.strptime(date_str.strip(), "%d.%m.%Y").isoformat()
    except ValueError:
        return None


class SostavCollector(BaseCollector):
    def __init__(self, queries: list[str] = None, browser_id: str = BROWSER_ID):
        self.queries = queries or ["Медиагруппа РИМ"]
        self.browser_id = browser_id

    async def collect(self) -> list[NewsItem]:
        # browser-act is sync CLI, run synchronously (fast enough)
        items: list[NewsItem] = []
        seen_urls: set[str] = set()

        for query in self.queries:
            for page in range(1, MAX_PAGES + 1):
                url = SOSTAV_SEARCH.format(query=quote(query), page=page)
                logger.info("Sostav scraping page %d: %r", page, query)

                # Open page — first launch downloads kernel (~60s), so use long timeout.
                # Even if it times out, the session keeps running in background.
                ba(["browser", "open", self.browser_id, url], timeout=90)

                # Wait for page to stabilise
                ba(["wait", "stable", "--timeout", "20000"], timeout=30)

                # Get markdown
                r = ba(["get", "markdown"], timeout=30)
                if not r:
                    logger.warning("No markdown for page %d query %r", page, query)
                    break

                markdown = r.get("markdown", "")
                articles = _parse_articles(markdown)
                logger.info("  Found %d articles on page %d", len(articles), page)

                if not articles:
                    break  # no more results

                for a in articles:
                    if a["url"] in seen_urls:
                        continue
                    seen_urls.add(a["url"])
                    items.append(NewsItem(
                        title=a["title"],
                        url=a["url"],
                        source=SOURCE,
                        source_type="browseract",
                        published_at=_parse_date(a["date"]),
                    ))

        logger.info("Sostav collected %d total items", len(items))
        ba(["session", "close", "--all"], timeout=10)
        return items
