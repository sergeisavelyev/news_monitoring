import logging
from email.utils import parsedate_to_datetime

import aiohttp
import feedparser

from collectors.base import BaseCollector
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 20
MAX_ITEMS_PER_SOURCE = 50


class RSSCollector(BaseCollector):
    """Collect articles from industry RSS feeds defined in config.INDUSTRY_RSS_SOURCES."""

    def __init__(self, sources: dict[str, str] = None):
        self.sources = sources or config.INDUSTRY_RSS_SOURCES

    async def collect(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            for name, url in self.sources.items():
                try:
                    batch = await self._fetch(session, name, url)
                    logger.info("RSS [%s]: %d items", name, len(batch))
                    items.extend(batch)
                except Exception as e:
                    logger.error("RSS [%s] error: %s", name, e)
        return items

    async def _fetch(self, session: aiohttp.ClientSession, name: str, url: str) -> list[NewsItem]:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)) as resp:
            if resp.status != 200:
                logger.warning("RSS [%s] HTTP %d", name, resp.status)
                return []
            raw = await resp.read()

        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            snippet = (entry.get("summary") or "").strip()
            published = self._parse_date(entry)
            items.append(NewsItem(
                title=title,
                url=link,
                source=name,
                source_type="rss",
                snippet=snippet,
                published_at=published,
            ))
        return items

    @staticmethod
    def _parse_date(entry) -> str | None:
        try:
            if hasattr(entry, "published"):
                return parsedate_to_datetime(entry.published).isoformat()
        except Exception:
            pass
        return None
