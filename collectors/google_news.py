import asyncio
import logging
import urllib.parse
from datetime import datetime
from email.utils import parsedate_to_datetime

import aiohttp
import feedparser

from collectors.base import BaseCollector
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ru&gl=RU&ceid=RU:ru"
REQUEST_DELAY = 7  # seconds between queries to avoid blocks


class GoogleNewsCollector(BaseCollector):
    def __init__(self, queries: list[str] = None):
        self.queries = queries or config.GOOGLE_NEWS_QUERIES

    async def collect(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            for i, query in enumerate(self.queries):
                if i > 0:
                    await asyncio.sleep(REQUEST_DELAY)
                fetched = await self._fetch_query(session, query)
                logger.info("Google News [%r]: %d items", query, len(fetched))
                items.extend(fetched)
        return items

    async def _fetch_query(self, session: aiohttp.ClientSession, query: str) -> list[NewsItem]:
        url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(query))
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    logger.warning("Google News HTTP %d for query %r", resp.status, query)
                    return []
                raw = await resp.read()
        except Exception as e:
            logger.error("Google News fetch error for %r: %s", query, e)
            return []

        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            # Google News wraps links — the real URL is in the link itself
            # (or sometimes needs extraction from redirect, but link is usually direct)
            published = self._parse_date(entry)
            snippet = entry.get("summary", "").strip()

            if not title or not link:
                continue

            items.append(NewsItem(
                title=title,
                url=link,
                source="Google News",
                source_type="google",
                snippet=snippet,
                published_at=published,
            ))
        return items

    @staticmethod
    def _parse_date(entry) -> str | None:
        try:
            if hasattr(entry, "published"):
                dt = parsedate_to_datetime(entry.published)
                return dt.isoformat()
        except Exception:
            pass
        return None
