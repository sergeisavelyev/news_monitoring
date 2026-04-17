import logging
from models.news_item import NewsItem
from ai.llm_client import LLMClient
import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — аналитик рекламного рынка. Сделай краткое резюме новости \
о компании «Медиагруппа РИМ» (Rim Group).

Ответь строго в JSON (без markdown):
{
  "summary": "2-3 предложения: суть новости",
  "topics": ["список тем: сделка, финансы, продукт, кадры, регулирование, ..."],
  "key_facts": ["ключевые факты и цифры из статьи"]
}"""


class Summarizer:
    def __init__(self, client: LLMClient = None):
        self.client = client or LLMClient()
        self.model = (
            config.LLM_SUMMARIZE_MODEL_ANTHROPIC
            if config.LLM_PROVIDER == "anthropic"
            else config.LLM_SUMMARIZE_MODEL_OPENAI
        )

    def summarize(self, item: NewsItem):
        """Enrich item with AI summary in-place."""
        text = (item.full_text or item.snippet or "")[:3000]
        user_msg = f"Заголовок: {item.title}\nИсточник: {item.source}\nТекст:\n{text}"

        result = self.client.chat(SYSTEM_PROMPT, user_msg, self.model, max_tokens=1024)
        if result is None:
            logger.warning("Summarizer returned None for: %s", item.title[:60])
            return

        item.ai_summary = result.get("summary", "")
        item.ai_topics = result.get("topics", [])
        item.ai_key_facts = result.get("key_facts", [])

        logger.info(
            "[Summarizer] %s | topics=%s",
            item.title[:60], item.ai_topics
        )
