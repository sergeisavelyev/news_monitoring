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

    matched_exclude = any(p.search(text) for p in _exclude)
    if matched_exclude:
        logger.info("EXCLUDE hit: %s", item.title[:80])
        return False

    # If INCLUDE list is empty — pass everything (LLM does the filtering)
    if not _include:
        return True

    matched_include = any(p.search(text) for p in _include)
    if matched_include:
        logger.info("INCLUDE hit: %s", item.title[:80])
        return True

    logger.info("No include match, skip: %r", item.title[:80])
    return False
