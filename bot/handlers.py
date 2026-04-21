import logging
from telegram import Update
from telegram.ext import ContextTypes
from storage.sqlite_storage import SQLiteStorage
from bot.formatter import format_article_card, _esc

logger = logging.getLogger(__name__)

# Storage is injected at bot startup via bot_data
def _storage(ctx: ContextTypes.DEFAULT_TYPE) -> SQLiteStorage:
    return ctx.bot_data["storage"]


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Привет!</b> Я бот мониторинга новостей о «Медиагруппа РИМ».\n\n"
        "Команды:\n"
        "/latest — последние 5 новостей\n"
        "/latest N — последние N новостей\n"
        "/stats — статистика по источникам\n"
        "/search ЗАПРОС — поиск в базе\n"
        "/digest — сводка за последние 24 часа\n"
        "/help — справка",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Справка по командам:</b>\n\n"
        "/latest [N] — последние N статей (макс. 20, по умолчанию 5)\n"
        "/stats — статистика: всего статей, разбивка по источникам\n"
        "/search ЗАПРОС — полнотекстовый поиск по заголовкам и резюме\n"
        "/digest — все новые статьи за последние 24 часа\n"
        "/start — приветствие\n"
        "/help — эта справка",
        parse_mode="HTML",
    )


async def cmd_latest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    limit = 5
    if ctx.args:
        try:
            limit = max(1, min(int(ctx.args[0]), 20))
        except ValueError:
            pass

    storage = _storage(ctx)
    items = storage.get_latest(limit=limit)

    if not items:
        await update.message.reply_text("Пока новостей нет.")
        return

    for i, item in enumerate(items, 1):
        text = format_article_card(item, index=i)
        await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    storage = _storage(ctx)
    s = storage.stats()

    lines = [f"📊 <b>Статистика мониторинга</b>\n", f"Всего статей: <b>{s['total']}</b>\n"]

    if s["by_source"]:
        lines.append("<b>По источникам:</b>")
        for src, count in sorted(s["by_source"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {_esc(src or '—')}: {count}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Использование: /search ЗАПРОС\nПример: /search цифровые экраны")
        return

    query = " ".join(ctx.args)
    storage = _storage(ctx)
    results = storage.search(query, limit=5)

    if not results:
        await update.message.reply_text(f'Ничего не найдено по запросу «{_esc(query)}».')
        return

    await update.message.reply_text(
        f"🔍 Найдено {len(results)} по «{_esc(query)}»:", parse_mode="HTML"
    )
    for i, item in enumerate(results, 1):
        text = format_article_card(item, index=i)
        await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def cmd_digest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime, timedelta, timezone
    storage = _storage(ctx)

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    all_items = storage.get_latest(limit=200)
    recent = [
        it for it in all_items
        if (it.get("created_at") or "") >= since[:19]
    ]

    if not recent:
        await update.message.reply_text("За последние 24 часа новых статей не найдено.")
        return

    await update.message.reply_text(
        f"📋 <b>Дайджест за 24 часа — {len(recent)} статей</b>", parse_mode="HTML"
    )
    for i, item in enumerate(recent, 1):
        text = format_article_card(item, index=i)
        await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
