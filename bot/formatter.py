import html
import json
import re
from models.news_item import NewsItem


def format_notification(item: NewsItem) -> str:
    """Format a NewsItem as an HTML Telegram message."""
    lines = ["📰 <b>Новая статья о «Медиагруппа РИМ»</b>\n"]

    lines.append(f"📌 <b>{_esc(item.title)}</b>")

    if item.source:
        lines.append(f"\n📁 Источник: {_esc(item.source)}")

    date = _format_date(item.published_at)
    if date:
        lines.append(f"📅 {date}")

    if item.ai_summary:
        lines.append(f"\n💡 <b>Резюме:</b>\n{_esc(item.ai_summary)}")
    elif item.snippet:
        lines.append(f"\n{_esc(_strip_html(item.snippet)[:300])}")

    if item.ai_topics:
        topics = item.ai_topics if isinstance(item.ai_topics, list) else json.loads(item.ai_topics or "[]")
        if topics:
            lines.append(f"\n🏷 {', '.join(topics)}")

    url = _usable_url(item.url)
    if url:
        lines.append(f"\n🔗 <a href=\"{url}\">Читать полностью</a>")

    return "\n".join(lines)


def format_article_card(item: dict, index: int = None) -> str:
    """Format a DB row dict as a short card for /latest."""
    prefix = f"{index}. " if index else ""
    title = _esc(item.get("title", ""))
    source = _esc(item.get("source") or "")
    date = _format_date(item.get("published_at") or item.get("created_at"))
    summary = item.get("ai_summary") or item.get("snippet") or ""
    url = item.get("url", "")

    lines = [f"{prefix}<b>{title}</b>"]
    meta = " | ".join(filter(None, [source, date]))
    if meta:
        lines.append(f"<i>{meta}</i>")
    if summary:
        lines.append(_esc(_strip_html(summary)[:250]))
    url = _usable_url(item.get("url", ""))
    if url:
        lines.append(f'<a href="{url}">Читать</a>')

    return "\n".join(lines)


def _format_date(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso[:19])
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return iso[:10] if iso else ""


def _usable_url(url: str | None) -> str:
    """Return the URL if it's usable in a browser, empty string otherwise."""
    if not url:
        return ""
    # Google News RSS encoded URLs don't open in browser
    if "news.google.com/rss/articles/" in url:
        return ""
    return url


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities from RSS/scraper content."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _esc(text: str) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
