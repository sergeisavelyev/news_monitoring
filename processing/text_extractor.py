"""
Text extractor: fetches full article text from a URL.

Strategy:
1. For dzen.ru/a/... articles — use browser-act-cli (JS-rendered, no direct HTML)
2. For all other URLs — aiohttp fetch + trafilatura extraction
3. Graceful fallback: item.full_text stays None on failure
"""
import asyncio
import logging

import aiohttp
import trafilatura

from models.news_item import NewsItem

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
FETCH_TIMEOUT = 15  # seconds per request
MAX_TEXT_CHARS = 5000  # trim to keep LLM costs manageable
DEFAULT_CONCURRENCY = 5  # parallel fetches


async def _fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[str, str] | tuple[None, None]:
    """Fetch HTML from URL, following redirects.
    Returns (html, final_url) or (None, None) on any error.
    The final_url may differ from url when redirects occur (e.g. Google News → real article).
    """
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                logger.debug("HTTP %d for %s", resp.status, url)
                return None, None
            final_url = str(resp.url)
            return await resp.text(errors="replace"), final_url
    except asyncio.TimeoutError:
        logger.debug("Timeout fetching %s", url)
        return None, None
    except Exception as e:
        logger.debug("Fetch error for %s: %s", url, e)
        return None, None


def _extract_text(html: str, url: str) -> str | None:
    """Extract article body from HTML using trafilatura."""
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not text:
        return None
    text = text.strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "…"
    return text


def _is_google_news_url(url: str) -> bool:
    return "news.google.com" in url


def _is_dzen_article(url: str) -> bool:
    """True for dzen.ru/a/... native articles (JS-rendered, need browser-act)."""
    return "dzen.ru/a/" in url


def _decode_google_news_url(url: str) -> str:
    """Resolve Google News encoded URL to real article URL (makes one HTTP request).
    Returns original url on failure.
    """
    try:
        from googlenewsdecoder import new_decoderv1
        result = new_decoderv1(url)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception as e:
        logger.debug("Google News decode failed for %s: %s", url, e)
    return url


def _ba_extract(url: str) -> str | None:
    """Extract text from a JS-heavy page using browser-act-cli."""
    from collectors.browser_act_utils import ba_get_markdown, DEFAULT_BROWSER_ID
    markdown = ba_get_markdown(DEFAULT_BROWSER_ID, url)
    if not markdown:
        return None
    # Keep only substantial lines (skip nav/UI noise)
    lines = [l.strip() for l in markdown.splitlines() if len(l.strip()) > 60]
    text = "\n".join(lines).strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "…"
    return text or None


async def _extract_one(item: NewsItem, session: aiohttp.ClientSession, sem: asyncio.Semaphore) -> None:
    """Fetch and populate item.full_text in place. Silent on failure."""
    loop = asyncio.get_event_loop()

    if _is_dzen_article(item.url):
        # Run browser-act in a thread to avoid blocking the event loop
        text = await loop.run_in_executor(None, _ba_extract, item.url)
    elif _is_google_news_url(item.url):
        # Decode Google News CBMi... URL to real article URL, then fetch
        fetch_url = await loop.run_in_executor(None, _decode_google_news_url, item.url)
        if fetch_url != item.url:
            item.url = fetch_url  # update so real URL is saved to DB and posted to Telegram
            logger.debug("Google News decoded: %s", fetch_url)
        async with sem:
            html, final_url = await _fetch_html(fetch_url, session)
        text = _extract_text(html, final_url or fetch_url) if html else None
    else:
        async with sem:
            html, final_url = await _fetch_html(item.url, session)
        text = _extract_text(html, final_url or item.url) if html else None

    if text:
        item.full_text = text
        logger.debug("Extracted %d chars from %s", len(text), item.url)


async def extract_texts(items: list[NewsItem], concurrency: int = DEFAULT_CONCURRENCY) -> None:
    """
    Fetch full article text for all items concurrently.
    Modifies items in-place (sets item.full_text). Silent on per-item failures.
    """
    if not items:
        return

    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[_extract_one(item, session, sem) for item in items])

    success = sum(1 for item in items if item.full_text)
    logger.info("Text extraction: %d/%d articles got full text", success, len(items))
