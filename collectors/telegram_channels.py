"""
Telegram channel collector using Telethon (MTProto API).

Reads posts from public Telegram channels and their comments.
Comments from a relevant post are concatenated and sent to LLM for summarization.

Setup (one-time):
  1. Get API_ID and API_HASH at https://my.telegram.org
  2. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE in .env
  3. On first run — you'll be asked to enter the SMS code (session is saved to disk)
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from collectors.base import BaseCollector
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(os.path.dirname(__file__), "..", "telegram_session")
SOURCE_TYPE = "telegram"

# How far back to look for new posts (hours)
LOOKBACK_HOURS = int(os.getenv("TELEGRAM_LOOKBACK_HOURS", "48"))

# Max comments to fetch per post (to limit LLM tokens)
MAX_COMMENTS = 50


def _build_post_url(channel_username: str, message_id: int) -> str:
    name = channel_username.lstrip("@")
    return f"https://t.me/{name}/{message_id}"


def _format_comments_for_llm(comments: list[dict]) -> str:
    """Concatenate comments into a readable block for LLM summarization."""
    lines = []
    for c in comments[:MAX_COMMENTS]:
        sender = c.get("sender", "user")
        text = c.get("text", "").strip()
        if text:
            lines.append(f"[{sender}]: {text}")
    return "\n".join(lines)


class TelegramChannelsCollector(BaseCollector):
    """
    Collect posts (and optionally comments) from Telegram channels.

    Each post becomes a NewsItem with:
      - title    = first line of the post (up to 120 chars)
      - snippet  = full post text
      - url      = t.me/channel/message_id
      - full_text = post text + formatted comments (if any)
    """

    def __init__(
        self,
        channels: list[str] = None,
        fetch_comments: bool = True,
        lookback_hours: int = LOOKBACK_HOURS,
    ):
        self.channels = channels or config.TELEGRAM_CHANNELS
        self.fetch_comments = fetch_comments
        self.lookback_hours = lookback_hours

    async def collect(self) -> list[NewsItem]:
        if not self.channels:
            logger.info("No Telegram channels configured — skipping")
            return []

        try:
            from telethon import TelegramClient
            from telethon.errors import FloodWaitError
        except ImportError:
            logger.error(
                "telethon not installed. Run: pip install telethon"
            )
            return []

        api_id = config.TELEGRAM_API_ID
        api_hash = config.TELEGRAM_API_HASH

        if not api_id or not api_hash:
            logger.error(
                "TELEGRAM_API_ID / TELEGRAM_API_HASH not set in .env"
            )
            return []

        items: list[NewsItem] = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        async with TelegramClient(SESSION_FILE, int(api_id), api_hash) as client:
            for channel in self.channels:
                try:
                    channel_items = await self._collect_channel(
                        client, channel, cutoff
                    )
                    items.extend(channel_items)
                except FloodWaitError as e:
                    logger.warning(
                        "Telegram rate limit hit for %s — waiting %ds", channel, e.seconds
                    )
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error("Failed to collect from %s: %s", channel, e)

        logger.info("Telegram collected %d total items from %d channels",
                    len(items), len(self.channels))
        return items

    async def _collect_channel(
        self, client, channel: str, cutoff: datetime
    ) -> list[NewsItem]:
        from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

        items: list[NewsItem] = []
        channel_name = channel.lstrip("@")
        logger.info("Collecting Telegram channel: @%s", channel_name)

        entity = await client.get_entity(channel)

        async for message in client.iter_messages(entity, limit=100):
            # Stop when we reach posts older than lookback window
            if message.date and message.date < cutoff:
                break

            # Skip empty / media-only posts
            if not message.text or len(message.text.strip()) < 10:
                continue

            post_text = message.text.strip()
            title = post_text.splitlines()[0][:120]
            post_url = _build_post_url(channel_name, message.id)

            full_text = post_text

            # Fetch comments if channel has discussion group
            if self.fetch_comments:
                comments = await self._fetch_comments(client, entity, message)
                if comments:
                    comments_block = _format_comments_for_llm(comments)
                    full_text = (
                        f"{post_text}\n\n"
                        f"--- Комментарии ({len(comments)}) ---\n"
                        f"{comments_block}"
                    )
                    logger.debug(
                        "  Post %d: fetched %d comments", message.id, len(comments)
                    )

            published_at = (
                message.date.isoformat() if message.date else None
            )

            items.append(NewsItem(
                title=title,
                url=post_url,
                source=f"Telegram @{channel_name}",
                source_type=SOURCE_TYPE,
                snippet=post_text[:500],
                published_at=published_at,
                full_text=full_text,
            ))

        logger.info("  @%s: collected %d posts", channel_name, len(items))
        return items

    async def _fetch_comments(
        self, client, entity, message
    ) -> list[dict]:
        """Fetch comments (replies) for a post. Returns [] if no discussion group."""
        try:
            from telethon.tl.functions.messages import GetRepliesRequest

            result = await client(GetRepliesRequest(
                peer=entity,
                msg_id=message.id,
                offset_id=0,
                offset_date=None,
                add_offset=0,
                limit=MAX_COMMENTS,
                max_id=0,
                min_id=0,
                hash=0,
            ))

            comments = []
            for msg in result.messages:
                if not msg.text:
                    continue
                sender = "user"
                if msg.sender:
                    sender = getattr(msg.sender, "username", None) or \
                             getattr(msg.sender, "first_name", "user") or "user"
                comments.append({"sender": str(sender), "text": msg.text})
            return comments

        except Exception:
            # Channel may not have comments enabled — silently skip
            return []
