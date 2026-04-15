"""
Dzen.ru news search collector using browser-act-cli.

Dzen search results markdown structure:
    Source Name
    26 марта в 12:27          ← date line (key anchor)
    Article title text
    ...snippet with *РИМ* emphasis...

Articles don't expose direct source URLs in markdown (JS-rendered links).
We parse the source + title + snippet and generate a dedup URL from their hash.
The snippet is rich enough for LLM relevance filtering.
"""
import hashlib
import logging
import re
from urllib.parse import quote

from collectors.base import BaseCollector
from collectors.browser_act_utils import ba, DEFAULT_BROWSER_ID
from models.news_item import NewsItem

logger = logging.getLogger(__name__)

DZEN_SEARCH = "https://dzen.ru/news/search?query={query}"
SOURCE = "Dzen"
SCROLL_ROUNDS = 4       # how many times to scroll down for more results
SCROLL_WAIT_MS = 3000   # wait after each scroll for lazy-loaded content

# Russian date patterns appearing in Dzen search results
_DATE_RE = re.compile(
    r"\d{1,2}\s+\w+\s+в\s+\d{1,2}:\d{2}"    # "26 марта в 12:27"
    r"|\d+\s+(час|мину|ден|дн|недел)\w*\s+назад"  # "2 часа назад"
    r"|(вчера|позавчера)\s+в\s+\d{1,2}:\d{2}",    # "вчера в 09:00"
    re.IGNORECASE,
)

# Strip markdown link syntax, returning only visible text
_DELINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
# Strip bold/italic emphasis markers
_DEEMPH = re.compile(r'\*+([^*]+)\*+')
# Skip lines that are clearly navigation/UI
_SKIP_LINE_RE = re.compile(
    r"^(войти|регистрация|подробнее|читать далее|ещё|загрузить|найти|"
    r"главная|меню|поиск|новости|статьи|видео|ролики|подписки|дзен|yandex|"
    r"релевантность|хронология|группировать|период|неделя|сегодня|за всё время)$",
    re.IGNORECASE,
)


def _clean(line: str) -> str:
    """Remove markdown links and emphasis, return plain text."""
    line = _DELINK.sub(r"\1", line)
    line = _DEEMPH.sub(r"\1", line)
    return line.strip()


def _parse_articles(markdown: str, query: str) -> list[dict]:
    """
    Parse Dzen search markdown into article dicts.
    Anchor: date line. Look back 1–3 lines for source name, forward for title+snippet.
    """
    lines = [_clean(l) for l in markdown.splitlines()]
    articles: list[dict] = []
    seen_keys: set[str] = set()

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line or _SKIP_LINE_RE.match(line):
            i += 1
            continue

        if _DATE_RE.search(line):
            date_str = line

            # Look back for source name (last non-empty, non-date, non-skip line)
            source_name = ""
            for j in range(i - 1, max(-1, i - 4), -1):
                candidate = lines[j]
                if candidate and not _DATE_RE.search(candidate) and not _SKIP_LINE_RE.match(candidate):
                    source_name = candidate
                    break

            # Collect forward lines: title + snippet (until next date anchor or empty run)
            text_parts: list[str] = []
            k = i + 1
            while k < len(lines) and len(text_parts) < 8:
                fwd = lines[k]
                if _DATE_RE.search(fwd):
                    break
                if fwd and not _SKIP_LINE_RE.match(fwd) and len(fwd) > 8:
                    text_parts.append(fwd)
                k += 1

            if source_name and text_parts:
                title = text_parts[0]
                snippet = " ".join(text_parts)
                dedup_key = f"{source_name}|{title[:80]}"
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    url_hash = hashlib.md5(dedup_key.encode()).hexdigest()[:16]
                    # Synthetic URL — stable for deduplication, links back to Dzen search
                    url = f"https://dzen.ru/news/search?query={quote(query)}#{url_hash}"
                    articles.append({
                        "title": title,
                        "url": url,
                        "source_label": source_name,
                        "date": date_str,
                        "snippet": snippet,
                    })
            i = k
            continue

        i += 1

    return articles


def _collect_with_scroll(browser_id: str, url: str) -> str:
    """Open page, scroll SCROLL_ROUNDS times, accumulate markdown."""
    ba(["browser", "open", browser_id, url], timeout=90)
    ba(["wait", "stable", "--timeout", "20000"], timeout=35)

    all_markdown = ""
    prev_len = 0

    for round_idx in range(SCROLL_ROUNDS + 1):  # +1 for initial read before first scroll
        r = ba(["get", "markdown"], timeout=30)
        chunk = r.get("markdown", "") if r else ""
        if len(chunk) > len(all_markdown):
            all_markdown = chunk
            logger.debug("Round %d: markdown %d chars", round_idx, len(all_markdown))

        if round_idx < SCROLL_ROUNDS:
            ba(["scroll", "down"], timeout=10)
            ba(["wait", "stable", "--timeout", str(SCROLL_WAIT_MS)], timeout=SCROLL_WAIT_MS // 1000 + 5)

        # Stop early if content stopped growing
        if round_idx > 0 and len(all_markdown) == prev_len:
            logger.debug("Content stable at %d chars after round %d, stopping scroll", len(all_markdown), round_idx)
            break
        prev_len = len(all_markdown)

    return all_markdown


class DzenCollector(BaseCollector):
    def __init__(self, queries: list[str] = None, browser_id: str = DEFAULT_BROWSER_ID):
        self.queries = queries or ["Медиагруппа РИМ"]
        self.browser_id = browser_id

    async def collect(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen_urls: set[str] = set()

        for query in self.queries:
            url = DZEN_SEARCH.format(query=quote(query))
            logger.info("Dzen: scraping %r", query)

            markdown = _collect_with_scroll(self.browser_id, url)
            if not markdown:
                logger.warning("Dzen: no markdown for query %r", query)
                continue

            articles = _parse_articles(markdown, query)
            logger.info("Dzen: parsed %d articles for %r", len(articles), query)

            for a in articles:
                if a["url"] in seen_urls:
                    continue
                seen_urls.add(a["url"])
                items.append(NewsItem(
                    title=a["title"],
                    url=a["url"],
                    source=f"Dzen / {a['source_label']}",
                    source_type="dzen",
                    snippet=a["snippet"],
                    published_at=a["date"],
                ))

        logger.info("Dzen: collected %d total", len(items))
        ba(["session", "close", "--all"], timeout=10)
        return items
