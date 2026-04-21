import logging
from telegram.ext import Application, CommandHandler
from bot.handlers import cmd_start, cmd_help, cmd_latest, cmd_stats, cmd_search, cmd_digest
from storage.sqlite_storage import SQLiteStorage
import config

logger = logging.getLogger(__name__)


def build_app(storage: SQLiteStorage) -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Make storage available to all handlers
    app.bot_data["storage"] = storage

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("digest", cmd_digest))

    logger.info("Bot application built, handlers registered")
    return app
