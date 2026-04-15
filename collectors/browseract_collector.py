import asyncio
import json
import logging
import time
from datetime import datetime

import aiohttp

from collectors.base import BaseCollector
from models.news_item import NewsItem
import config

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"finished", "completed", "done", "success"}
FAILURE_STATUSES = {"failed", "error", "cancelled"}
POLL_INTERVAL = 5   # seconds
POLL_TIMEOUT = 180  # seconds


class BrowserActCollector(BaseCollector):
    """
    Runs one or more BrowserAct workflows and converts results to NewsItems.

    Each workflow is identified by its ID from .env.
    Workflows are started in parallel, then polled until completion.
    """

    def __init__(self, workflows: list[dict] = None):
        """
        workflows: list of {"workflow_id": str, "source": str, "source_type": str}
        Defaults to all configured workflows from config.
        """
        self.workflows = workflows or self._default_workflows()
        self.headers = {
            "Authorization": f"Bearer {config.BROWSERACT_API_KEY}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _default_workflows() -> list[dict]:
        wf = []
        if config.BROWSERACT_WORKFLOW_SOSTAV:
            wf.append({"workflow_id": config.BROWSERACT_WORKFLOW_SOSTAV,
                       "source": "Sostav", "source_type": "browseract"})
        if config.BROWSERACT_WORKFLOW_ADINDEX:
            wf.append({"workflow_id": config.BROWSERACT_WORKFLOW_ADINDEX,
                       "source": "AdIndex", "source_type": "browseract"})
        if config.BROWSERACT_WORKFLOW_OUTDOOR:
            wf.append({"workflow_id": config.BROWSERACT_WORKFLOW_OUTDOOR,
                       "source": "Outdoor.ru", "source_type": "browseract"})
        return wf

    async def collect(self) -> list[NewsItem]:
        if not self.workflows:
            logger.warning("No BrowserAct workflows configured")
            return []

        async with aiohttp.ClientSession(headers=self.headers) as session:
            # Start all workflows in parallel
            task_ids = await asyncio.gather(
                *[self._start_workflow(session, wf) for wf in self.workflows]
            )

            # Poll all tasks in parallel
            results = await asyncio.gather(
                *[
                    self._poll_and_fetch(session, task_id, wf)
                    for task_id, wf in zip(task_ids, self.workflows)
                    if task_id
                ]
            )

        items: list[NewsItem] = []
        for batch in results:
            items.extend(batch)
        return items

    async def _start_workflow(self, session: aiohttp.ClientSession, wf: dict) -> str | None:
        url = f"{config.BROWSERACT_BASE_URL}/run-task"
        body = {"workflow_id": wf["workflow_id"]}
        try:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    logger.error("BrowserAct start error [%s]: %s", wf["source"], data)
                    return None
                task_id = data.get("id") or data.get("task_id")
                logger.info("BrowserAct [%s] started → task_id=%s", wf["source"], task_id)
                return task_id
        except Exception as e:
            logger.error("BrowserAct start exception [%s]: %s", wf["source"], e)
            return None

    async def _poll_and_fetch(
        self, session: aiohttp.ClientSession, task_id: str, wf: dict
    ) -> list[NewsItem]:
        deadline = time.monotonic() + POLL_TIMEOUT
        url_status = f"{config.BROWSERACT_BASE_URL}/get-task-status?task_id={task_id}"

        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                async with session.get(url_status, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json(content_type=None)
            except Exception as e:
                logger.warning("BrowserAct poll error [%s]: %s", wf["source"], e)
                continue

            status = data.get("status") or data.get("state") or "unknown"
            logger.debug("BrowserAct [%s] status=%s", wf["source"], status)

            if status in SUCCESS_STATUSES:
                return await self._fetch_result(session, task_id, wf)
            if status in FAILURE_STATUSES:
                logger.error("BrowserAct [%s] task failed: %s", wf["source"], data)
                return []

        logger.error("BrowserAct [%s] timeout after %ds", wf["source"], POLL_TIMEOUT)
        return []

    async def _fetch_result(
        self, session: aiohttp.ClientSession, task_id: str, wf: dict
    ) -> list[NewsItem]:
        url = f"{config.BROWSERACT_BASE_URL}/get-task?task_id={task_id}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.error("BrowserAct fetch result error [%s]: %s", wf["source"], e)
            return []

        raw = (data.get("output") or {}).get("string") or ""
        if not raw:
            logger.warning("BrowserAct [%s] empty output", wf["source"])
            return []

        try:
            records = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("BrowserAct [%s] JSON parse error: %s | raw: %r", wf["source"], e, raw[:200])
            return []

        items = []
        for r in records if isinstance(records, list) else []:
            title = (r.get("title") or "").strip()
            url_art = (r.get("url") or "").strip()
            if not title or not url_art:
                continue
            items.append(NewsItem(
                title=title,
                url=url_art,
                source=wf["source"],
                source_type=wf["source_type"],
                snippet=r.get("snippet") or "",
                published_at=self._parse_date(r.get("date") or ""),
            ))

        logger.info("BrowserAct [%s] → %d items", wf["source"], len(items))
        return items

    @staticmethod
    def _parse_date(date_str: str) -> str | None:
        """Parse DD.MM.YYYY → ISO 8601."""
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).isoformat()
            except (ValueError, AttributeError):
                continue
        return None
