import logging
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from collectors.google_news import GoogleNewsCollector
from processing.pipeline import Pipeline
from storage.sqlite_storage import SQLiteStorage
from bot.notifier import TelegramNotifier
import config

logger = logging.getLogger(__name__)


async def _run_pipeline(storage: SQLiteStorage, notifier: TelegramNotifier, source: str = "all"):
    """Run one pipeline cycle: collect → process → notify."""
    logger.info("Scheduler: starting pipeline for source=%s", source)
    try:
        async with aiohttp.ClientSession() as session:
            collectors = []
            if source in ("all", "google"):
                collectors.append(GoogleNewsCollector(session))
            if source in ("all", "sostav"):
                from collectors.sostav_collector import SostavCollector
                collectors.append(SostavCollector(session))
            if source in ("all", "dzen"):
                from collectors.dzen_collector import DzenCollector
                collectors.append(DzenCollector(session))
            if source in ("all", "adindex"):
                from collectors.adindex_collector import AdIndexCollector
                collectors.append(AdIndexCollector(session))

            raw_items = []
            for c in collectors:
                try:
                    items = await c.collect()
                    raw_items.extend(items)
                    logger.info("%s: collected %d items", c.__class__.__name__, len(items))
                except Exception as e:
                    logger.error("%s error: %s", c.__class__.__name__, e)

        pipeline = Pipeline(storage=storage)
        saved = await pipeline.run(raw_items)

        # Notify for newly saved articles (pipeline returns saved NewsItems)
        if notifier and saved:
            for item in saved:
                sent = await notifier.send(item)
                if sent and item.content_hash:
                    # Find the DB id by hash to mark as notified
                    with storage._get_conn() as conn:
                        row = conn.execute(
                            "SELECT id FROM news WHERE content_hash = ?", (item.content_hash,)
                        ).fetchone()
                        if row:
                            storage.mark_notified(row["id"])

        logger.info("Scheduler cycle done: %d articles saved", len(saved))
    except Exception as e:
        logger.error("Scheduler pipeline error: %s", e)


def build_scheduler(storage: SQLiteStorage, notifier: TelegramNotifier) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Google News — every 30 minutes
    scheduler.add_job(
        _run_pipeline,
        "interval",
        minutes=config.SCHEDULE.get("google_news", 30),
        id="google_news",
        kwargs={"storage": storage, "notifier": notifier, "source": "google"},
    )

    # Sostav + Dzen + AdIndex — every 6 hours (less frequent, browser-act heavy)
    scheduler.add_job(
        _run_pipeline,
        "interval",
        hours=6,
        id="browser_sources",
        kwargs={"storage": storage, "notifier": notifier, "source": "all"},
    )

    logger.info("Scheduler built: google_news every %d min, browser sources every 6h",
                config.SCHEDULE.get("google_news", 30))
    return scheduler
