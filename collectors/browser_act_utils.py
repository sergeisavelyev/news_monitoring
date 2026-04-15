"""
Shared browser-act-cli utilities.
Browser ID created once: browser-act browser create "scraper"
"""
import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Created with: browser-act browser create "sostav-scraper"
DEFAULT_BROWSER_ID = "90674564485747216"


def find_browser_act() -> str:
    for candidate in [
        shutil.which("browser-act"),
        r"C:\Users\admin\.local\bin\browser-act.exe",
        r"C:\Users\admin\.local\bin\browser-act",
    ]:
        if candidate and shutil.os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError("browser-act not found. Run: uv tool install browser-act-cli --python 3.12")


def ba(args: list[str], timeout: int = 30) -> dict | None:
    """Run a browser-act command, return parsed JSON or None on failure."""
    try:
        exe = find_browser_act()
    except FileNotFoundError as e:
        logger.error("%s", e)
        return None
    cmd = [exe] + args + ["--format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8")
        if result.returncode != 0:
            logger.warning("browser-act stderr: %s", result.stderr[:300])
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.error("browser-act timeout (%ds): %s", timeout, " ".join(args[:4]))
        return None
    except Exception as e:
        logger.error("browser-act error: %s", e)
        return None


def ba_get_markdown(browser_id: str, url: str, wait_ms: int = 20000) -> str | None:
    """Open URL in browser, wait for stable, return markdown content or None."""
    ba(["browser", "open", browser_id, url], timeout=90)
    ba(["wait", "stable", "--timeout", str(wait_ms)], timeout=wait_ms // 1000 + 10)
    r = ba(["get", "markdown"], timeout=30)
    if not r:
        return None
    return r.get("markdown", "") or None
