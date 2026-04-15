import logging
from models.news_item import NewsItem
from processing.content_hasher import compute_hash
from processing.deduplicator import Deduplicator
from processing import keyword_filter
from ai.relevance_filter import RelevanceFilter
from ai.summarizer import Summarizer
from storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        storage: SQLiteStorage,
        relevance_filter: RelevanceFilter = None,
        summarizer: Summarizer = None,
        skip_llm: bool = False,
        skip_extract: bool = False,
    ):
        self.storage = storage
        self.deduplicator = Deduplicator(storage)
        self.relevance_filter = relevance_filter or RelevanceFilter()
        self.summarizer = summarizer or Summarizer()
        self.skip_llm = skip_llm
        self.skip_extract = skip_extract  # skip full-text fetch (for quick tests)

    async def run(self, items: list[NewsItem]) -> list[NewsItem]:
        """Process a list of raw items. Returns items that passed the full pipeline."""
        self.deduplicator.reset_run_cache()
        saved: list[NewsItem] = []

        stats = {"total": len(items), "dedup": 0, "keyword": 0, "llm": 0, "saved": 0}

        # Steps 1-3: hash, dedup, keyword filter (sync, no I/O)
        candidates: list[NewsItem] = []
        for item in items:
            item.content_hash = compute_hash(item.title, item.url)

            if self.deduplicator.is_duplicate(item):
                stats["dedup"] += 1
                continue

            if not keyword_filter.passes(item):
                stats["keyword"] += 1
                continue

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

            row_id = self.storage.save(item)
            if row_id:
                stats["saved"] += 1
                saved.append(item)

        logger.info(
            "Pipeline done | total=%d dedup=%d keyword_filtered=%d llm_filtered=%d saved=%d",
            stats["total"], stats["dedup"], stats["keyword"], stats["llm"], stats["saved"],
        )
        return saved
