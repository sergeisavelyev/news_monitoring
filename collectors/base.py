from abc import ABC, abstractmethod
from models.news_item import NewsItem


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self) -> list[NewsItem]:
        """Collect raw news items from the source."""
        ...
