"""
News monitor — one-shot runner.

Collect news → pipeline (dedup/filter/LLM) → post new articles to Telegram → exit.
Run manually or via Windows Task Scheduler 1-2x per day.

To switch from personal chat to a channel: set TELEGRAM_CHAT_ID=-100XXXXXXXXXX in .env
and add the bot as an admin to that channel.
"""
import asyncio
import logging
import sys
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def collect_all() -> list:
    from collectors.google_news import GoogleNewsCollector
    from collectors.browseract_collector import BrowserActCollector

    items = []

    try:
        batch = await GoogleNewsCollector(queries=config.GOOGLE_NEWS_QUERIES).collect()
        logger.info("Google News: %d items", len(batch))
        items.extend(batch)
    except Exception as e:
        logger.error("Google News error: %s", e)

    try:
        batch = await BrowserActCollector().collect()
        logger.info("BrowserAct: %d items", len(batch))
        items.extend(batch)
    except Exception as e:
        logger.error("BrowserAct error: %s", e)

    try:
        from collectors.sostav_collector import SostavCollector
        batch = await SostavCollector().collect()
        logger.info("Sostav: %d items", len(batch))
        items.extend(batch)
    except Exception as e:
        logger.error("Sostav error: %s", e)

    try:
        from collectors.adindex_collector import AdIndexCollector
        batch = await AdIndexCollector().collect()
        logger.info("AdIndex: %d items", len(batch))
        items.extend(batch)
    except Exception as e:
        logger.error("AdIndex error: %s", e)

    try:
        from collectors.dzen_collector import DzenCollector
        batch = await DzenCollector().collect()
        logger.info("Dzen: %d items", len(batch))
        items.extend(batch)
    except Exception as e:
        logger.error("Dzen error: %s", e)

    try:
        from collectors.telegram_channels import TelegramChannelsCollector
        batch = await TelegramChannelsCollector().collect()
        logger.info("Telegram channels: %d items", len(batch))
        items.extend(batch)
    except Exception as e:
        logger.error("Telegram channels error: %s", e)

    return items


def print_saved(saved: list) -> None:
    print("\n" + "=" * 60)
    print(f"RESULTS: {len(saved)} new article(s) saved")
    print("=" * 60)
    for item in saved:
        print(f"\n• {item.title}")
        print(f"   Source : {item.source}")
        print(f"   URL    : {item.url}")
        if item.ai_summary:
            print(f"   Summary: {item.ai_summary}")
        if item.ai_topics:
            print(f"   Topics : {', '.join(item.ai_topics)}")
    if not saved:
        print("\nNo new relevant articles found.")


async def post_unnotified(storage) -> int:
    from telegram import Bot
    from bot.notifier import TelegramNotifier
    from models.news_item import NewsItem

    rows = storage.get_unnotified()
    if not rows:
        return 0

    posted = 0
    async with Bot(token=config.TELEGRAM_BOT_TOKEN) as bot:
        notifier = TelegramNotifier(bot, config.TELEGRAM_CHAT_ID)
        for row in rows:
            item = NewsItem(
                title=row["title"],
                url=row["url"],
                source=row.get("source") or "",
                source_type=row.get("source_type") or "",
                snippet=row.get("snippet") or "",
                published_at=row.get("published_at"),
                ai_summary=row.get("ai_summary"),
            )
            sent = await notifier.send(item)
            if sent:
                storage.mark_notified(row["id"])
                posted += 1

    return posted


async def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        return
    if not config.TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID not set in .env")
        return

    from storage.sqlite_storage import SQLiteStorage
    from processing.pipeline import Pipeline

    storage = SQLiteStorage()

    # 1. Collect from all sources
    logger.info("=== Collecting news ===")
    items = await collect_all()
    logger.info("Total collected: %d items", len(items))

    # 2. Pipeline: dedup → keyword filter → date filter → LLM → save
    # On repeat runs: already-seen articles are skipped by hash before LLM is called
    pipeline = Pipeline(storage=storage)
    saved = await pipeline.run(items)

    # 3. Console output
    print_saved(saved)

    # 4. Post all unnotified articles to Telegram
    # (also catches leftovers from previous runs that weren't posted)
    posted = await post_unnotified(storage)

    if posted:
        print(f"\nPosted {posted} article(s) to Telegram.")
    else:
        print("\nNothing new to post.")

    stats = storage.stats()
    print(f"DB total: {stats['total']} articles")
    logger.info("=== Done ===")


if __name__ == "__main__":
    asyncio.run(main())
