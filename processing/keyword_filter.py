import re
import logging
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)

_include = [re.compile(p, re.IGNORECASE) for p in config.INCLUDE_PATTERNS]
_exclude = [re.compile(p, re.IGNORECASE) for p in config.EXCLUDE_PATTERNS]


def _text(item: NewsItem) -> str:
    return " ".join(filter(None, [item.title, item.snippet, item.full_text]))


def passes(item: NewsItem) -> bool:
    text = _text(item)

    matched_include = any(p.search(text) for p in _include)
    matched_exclude = any(p.search(text) for p in _exclude)

    if matched_include:
        logger.info("INCLUDE hit: %s", item.title[:80])
        return True
    if matched_exclude:
        logger.info("EXCLUDE hit (no include): %s", item.title[:80])
        return False

    logger.info("No pattern match, skip: %r", item.title[:80])
    return False
