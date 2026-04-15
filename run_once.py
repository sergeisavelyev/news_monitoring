"""
One-shot pipeline runner for debugging and testing.

Usage:
    python run_once.py                  # full pipeline (LLM on)
    python run_once.py --skip-llm       # keyword filter only, no LLM calls
    python run_once.py --skip-llm --limit 2   # limit queries
"""
import asyncio
import argparse
import logging
import sys
import io

# Force UTF-8 output on Windows to support Unicode / emoji
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import config  # loads .env

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("run_once")


async def main(skip_llm: bool, limit: int | None, source: str, skip_extract: bool = False):
    from collectors.google_news import GoogleNewsCollector
    from collectors.browseract_collector import BrowserActCollector
    from processing.pipeline import Pipeline
    from storage.sqlite_storage import SQLiteStorage

    storage = SQLiteStorage()

    logger.info("=== Starting pipeline ===")
    logger.info("LLM: %s | skip_llm=%s | source=%s", config.LLM_PROVIDER, skip_llm, source)

    items = []

    if source in ("google", "all"):
        queries = config.GOOGLE_NEWS_QUERIES
        if limit:
            queries = queries[:limit]
        logger.info("Queries: %s", queries)
        collector = GoogleNewsCollector(queries=queries)
        batch = await collector.collect()
        logger.info("Collected %d items from Google News", len(batch))
        items.extend(batch)

    if source in ("browseract", "all"):
        ba_collector = BrowserActCollector()
        batch = await ba_collector.collect()
        logger.info("Collected %d items from BrowserAct", len(batch))
        items.extend(batch)

    if source in ("sostav", "all"):
        from collectors.sostav_collector import SostavCollector
        sostav = SostavCollector()
        batch = await sostav.collect()
        logger.info("Collected %d items from Sostav", len(batch))
        items.extend(batch)

    if source in ("adindex", "all"):
        from collectors.adindex_collector import AdIndexCollector
        adindex = AdIndexCollector()
        batch = await adindex.collect()
        logger.info("Collected %d items from AdIndex", len(batch))
        items.extend(batch)

    if source in ("dzen", "all"):
        from collectors.dzen_collector import DzenCollector
        dzen = DzenCollector()
        batch = await dzen.collect()
        logger.info("Collected %d items from Dzen", len(batch))
        items.extend(batch)

    if source in ("telegram", "all"):
        from collectors.telegram_channels import TelegramChannelsCollector
        tg = TelegramChannelsCollector()
        batch = await tg.collect()
        logger.info("Collected %d items from Telegram", len(batch))
        items.extend(batch)

    logger.info("Total collected: %d items", len(items))

    if items:
        print("\n--- RAW ITEMS ---")
        for i, item in enumerate(items, 1):
            print(f"  [{i}] {item.source} | {item.title[:100]!r}")
            print(f"       URL: {item.url}")
        print("-" * 40)

    pipeline = Pipeline(storage=storage, skip_llm=skip_llm, skip_extract=skip_extract)
    saved = await pipeline.run(items)

    print("\n" + "=" * 60)
    print(f"RESULTS: {len(saved)} new article(s) saved")
    print("=" * 60)

    for item in saved:
        sentiment_icon = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}.get(
            item.ai_sentiment or "", "⚪"
        )
        print(f"\n{sentiment_icon} {item.title}")
        print(f"   Source : {item.source}")
        print(f"   URL    : {item.url}")
        if item.ai_summary:
            print(f"   Summary: {item.ai_summary}")
        if item.ai_topics:
            print(f"   Topics : {', '.join(item.ai_topics)}")

    if not saved:
        print("\nNo new relevant articles found.")

    stats = storage.stats()
    print(f"\nDB total: {stats['total']} articles")
    print(f"By sentiment: {stats['by_sentiment']}")
    print(f"By source:    {stats['by_source']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM calls (keyword filter only)")
    parser.add_argument("--skip-extract", action="store_true", help="Skip full-text extraction (faster, no trafilatura)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of Google News queries")
    parser.add_argument(
        "--source", default="google",
        choices=["google", "browseract", "sostav", "adindex", "dzen", "telegram", "all"],
        help="Data source to use (default: google)"
    )
    args = parser.parse_args()

    asyncio.run(main(skip_llm=args.skip_llm, limit=args.limit, source=args.source, skip_extract=args.skip_extract))
