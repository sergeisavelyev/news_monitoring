import logging
from models.news_item import NewsItem
from ai.llm_client import LLMClient
import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — аналитик медиамониторинга компании «Медиагруппа РИМ» (Rim Group) — \
крупного российского оператора наружной рекламы (OOH/DOOH). Штаб-квартира в Казани, \
работает по всей России. CEO — Илья Фомин.

Твоя задача — определить, релевантна ли новость для мониторинга этой компании.

Считай релевантным:
- Прямые упоминания «РИМ», «Медиагруппа РИМ», «Rim Group», «rimgroup», «Илья Фомин», «ITL Group»
- Новости о рынке наружной рекламы в России (OOH/DOOH) — компания является ключевым игроком
- Новости о конкурентах: Gallery, Russ Outdoor, BigBoard, «Постер», «Витрина»
- Отраслевые события: НРФ, ЭВК, AdIndex City Conference, АРИР — РИМ там участвует
- Новости о наружной рекламе в Казани, Татарстане — РИМ доминирует в этом регионе
- Регуляторные изменения в сфере наружной рекламы в России
- Технологии DOOH, цифровые экраны, programmatic OOH

Считай НЕрелевантным:
- Новости о городе Рим (Италия), Римской империи, римском праве
- Политика, спорт, медицина — если нет связи с рекламным рынком
- Иностранные рынки рекламы без упоминания российских операторов

Ответь строго в JSON (без markdown):
{
  "relevant": true или false,
  "confidence": число от 0.0 до 1.0,
  "reason": "краткое объяснение на русском"
}"""


class RelevanceFilter:
    def __init__(self, client: LLMClient = None, threshold: float = None):
        self.client = client or LLMClient()
        self.threshold = threshold if threshold is not None else config.RELEVANCE_THRESHOLD
        self.model = (
            config.LLM_FILTER_MODEL_ANTHROPIC
            if config.LLM_PROVIDER == "anthropic"
            else config.LLM_FILTER_MODEL_OPENAI
        )

    def check(self, item: NewsItem) -> bool:
        """Returns True if the item is relevant. Sets item.ai_relevance."""
        text = (item.snippet or item.full_text or "")[:1500]
        user_msg = f"Заголовок: {item.title}\nИсточник: {item.source}\nТекст: {text}"

        result = self.client.chat(SYSTEM_PROMPT, user_msg, self.model, max_tokens=256)
        if result is None:
            logger.warning("LLM filter returned None for: %s", item.title[:60])
            return False

        relevant = result.get("relevant", False)
        confidence = float(result.get("confidence", 0.0))
        reason = result.get("reason", "")

        item.ai_relevance = confidence
        passes = relevant and confidence >= self.threshold

        logger.info(
            "[LLM filter] %s | relevant=%s conf=%.2f | %s",
            item.title[:60], relevant, confidence, reason
        )
        return passes
