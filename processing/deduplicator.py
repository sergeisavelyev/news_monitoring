import logging
from models.news_item import NewsItem
from storage.sqlite_storage import SQLiteStorage
from processing.content_hasher import compute_hash

logger = logging.getLogger(__name__)


class Deduplicator:
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage
        # In-memory set for dedup within a single pipeline run
        self._seen: set[str] = set()

    def is_duplicate(self, item: NewsItem) -> bool:
        h = item.content_hash or compute_hash(item.title, item.url)
        item.content_hash = h

        if h in self._seen:
            logger.debug("In-run duplicate: %s", item.title[:60])
            return True
        if self.storage.exists(h):
            logger.debug("DB duplicate: %s", item.title[:60])
            return True
        if self.storage.url_exists(item.url):
            logger.debug("URL duplicate: %s", item.url)
            return True

        self._seen.add(h)
        return False

    def reset_run_cache(self):
        self._seen.clear()
