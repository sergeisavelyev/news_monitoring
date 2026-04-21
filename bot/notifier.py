import logging
from telegram import Bot
from telegram.error import TelegramError
from models.news_item import NewsItem
from bot.formatter import format_notification

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot: Bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id

    async def send(self, item: NewsItem) -> bool:
        """Send a notification for a new article. Returns True on success."""
        try:
            text = format_notification(item)
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            logger.info("Notified: %s", item.title[:80])
            return True
        except TelegramError as e:
            logger.error("Telegram send error: %s", e)
            return False

    async def send_text(self, text: str) -> bool:
        """Send arbitrary HTML text message."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return True
        except TelegramError as e:
            logger.error("Telegram send error: %s", e)
            return False
