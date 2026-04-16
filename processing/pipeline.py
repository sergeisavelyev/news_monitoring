import logging
from datetime import datetime, timezone, timedelta
from models.news_item import NewsItem
from processing.content_hasher import compute_hash
from processing.deduplicator import Deduplicator
from processing import keyword_filter
from ai.relevance_filter import RelevanceFilter
from ai.summarizer import Summarizer
from storage.sqlite_storage import SQLiteStorage
import config

logger = logging.getLogger(__name__)


def _is_too_old(item: NewsItem) -> bool:
    """Returns True if published_at is older than MAX_ARTICLE_AGE_DAYS."""
    if not item.published_at:
        return False  # no date → don't discard
    try:
        dt = datetime.fromisoformat(item.published_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt
        return age > timedelta(days=config.MAX_ARTICLE_AGE_DAYS)
    except Exception:
        return False


class Pipeline:
    def __init__(
        self,
        storage: SQLiteStorage,
        relevance_filter: RelevanceFilter = None,
        summarizer: Summarizer = None,
        skip_llm: bool = False,
        skip_extract: bool = False,
        skip_keyword: bool = False,
        debug_mode: bool = False,
    ):
        self.storage = storage
        self.deduplicator = Deduplicator(storage)
        self.relevance_filter = relevance_filter or RelevanceFilter()
        self.summarizer = summarizer or Summarizer()
        self.skip_llm = skip_llm
        self.skip_extract = skip_extract
        self.skip_keyword = skip_keyword
        self.debug_mode = debug_mode  # saves rejected items too, for debug view

    async def run(self, items: list[NewsItem]) -> list[NewsItem]:
        """Process a list of raw items. Returns items that passed the full pipeline."""
        self.deduplicator.reset_run_cache()
        saved: list[NewsItem] = []

        stats = {"total": len(items), "dedup": 0, "old": 0, "keyword": 0, "llm": 0, "saved": 0}

        # Steps 1-3: hash, dedup, date filter, keyword filter (sync, no I/O)
        candidates: list[NewsItem] = []
        for item in items:
            item.content_hash = compute_hash(item.title, item.url)

            if self.deduplicator.is_duplicate(item):
                stats["dedup"] += 1
                continue

            if _is_too_old(item):
                stats["old"] += 1
                logger.debug("Too old, skip: %s (%s)", item.title[:60], item.published_at)
                continue

            if not self.skip_keyword and not keyword_filter.passes(item):
                stats["keyword"] += 1
                if self.debug_mode:
                    self.storage.save(item, filter_status="keyword_rejected")
                continue
            elif self.skip_keyword:
                item.passed_keyword_filter = False

            item.passed_keyword_filter = True
            candidates.append(item)

        # Step 3.5: fetch full text for keyword-passing candidates (async, concurrent)
        if candidates and not self.skip_extract:
            from processing.text_extractor import extract_texts
            await extract_texts(candidates)

        # Steps 4-6: LLM filter, summarize, save
        for item in candidates:
            if not self.skip_llm:
                if not self.relevance_filter.check(item):
                    stats["llm"] += 1
                    continue
                item.passed_llm_filter = True
                self.summarizer.summarize(item)
            else:
                item.passed_llm_filter = True

            # --no-filter mode: mark unfiltered so normal view excludes them
            status = "unfiltered" if self.skip_keyword and not item.passed_keyword_filter else "saved"
            row_id = self.storage.save(item, filter_status=status)
            if row_id:
                stats["saved"] += 1
                saved.append(item)

        logger.info(
            "Pipeline done | total=%d dedup=%d old=%d keyword_filtered=%d llm_filtered=%d saved=%d",
            stats["total"], stats["dedup"], stats["old"], stats["keyword"], stats["llm"], stats["saved"],
        )
        return saved
