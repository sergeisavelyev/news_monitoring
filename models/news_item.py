from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class NewsItem:
    title: str
    url: str
    source: str                          # "Google News", "Sostav", etc.
    source_type: str                     # "rss" | "google" | "browseract" | "telegram"
    snippet: str = ""
    published_at: Optional[str] = None  # ISO 8601
    full_text: Optional[str] = None
    content_hash: Optional[str] = None

    # AI fields
    ai_summary: Optional[str] = None
    ai_sentiment: Optional[str] = None  # positive | neutral | negative
    ai_relevance: Optional[float] = None
    ai_topics: Optional[list] = field(default_factory=list)
    ai_key_facts: Optional[list] = field(default_factory=list)

    # Flags
    passed_keyword_filter: bool = False
    passed_llm_filter: bool = False

    def __repr__(self):
        return f"NewsItem(source={self.source!r}, title={self.title[:60]!r})"
