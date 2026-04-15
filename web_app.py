"""
Web dashboard for news_monitor.

Run:  python web_app.py
Open: http://localhost:8000
"""
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, StreamingResponse

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "news_monitor.db"

app = FastAPI()


def get_articles(limit: int = 200) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM news ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    if not DB_PATH.exists():
        return {"total": 0, "by_source": {}, "by_sentiment": {}}
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
    by_source = dict(conn.execute("SELECT source, COUNT(*) FROM news GROUP BY source").fetchall())
    by_sentiment = dict(conn.execute(
        "SELECT ai_sentiment, COUNT(*) FROM news WHERE ai_sentiment IS NOT NULL GROUP BY ai_sentiment"
    ).fetchall())
    conn.close()
    return {"total": total, "by_source": by_source, "by_sentiment": by_sentiment}


HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>News Monitor — РИМ</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #f5f5f7; color: #1d1d1f; }

  /* ── Header ── */
  header {
    background: #fff;
    border-bottom: 1px solid #e0e0e0;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    position: sticky; top: 0; z-index: 10;
  }
  header h1 { font-size: 15px; font-weight: 600; white-space: nowrap; }
  .controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; flex: 1; }
  select, button {
    height: 32px; border-radius: 6px; border: 1px solid #ccc;
    font-size: 13px; padding: 0 10px; cursor: pointer;
  }
  select { background: #fff; }
  .cb-label { font-size: 13px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
  #run-btn {
    background: #0071e3; color: #fff; border-color: #0071e3;
    font-weight: 600; padding: 0 16px;
  }
  #run-btn:hover { background: #0077ed; }
  #run-btn:disabled { background: #999; border-color: #999; cursor: not-allowed; }
  .stats { font-size: 12px; color: #666; margin-left: auto; white-space: nowrap; }

  /* ── Layout ── */
  .layout { display: grid; grid-template-columns: 380px 1fr; height: calc(100vh - 57px); }

  /* ── Terminal ── */
  .terminal-wrap {
    background: #1a1a1a; display: flex; flex-direction: column;
    border-right: 1px solid #333;
  }
  .terminal-title {
    color: #888; font-size: 11px; padding: 8px 12px;
    border-bottom: 1px solid #2a2a2a; text-transform: uppercase; letter-spacing: .5px;
  }
  #terminal {
    flex: 1; overflow-y: auto; padding: 10px 12px;
    font-family: 'Menlo', 'Consolas', monospace; font-size: 11px;
    line-height: 1.55; color: #ccc;
  }
  #terminal .line-err  { color: #f97575; }
  #terminal .line-info { color: #6ec6f5; }
  #terminal .line-warn { color: #f5c842; }
  #terminal .line-ok   { color: #6fcf87; }
  #terminal .line-sep  { color: #555; }

  /* ── Articles ── */
  .articles-wrap { overflow-y: auto; padding: 16px; }
  .articles-wrap h2 { font-size: 13px; color: #666; margin-bottom: 12px; font-weight: 500; }
  .articles { display: flex; flex-direction: column; gap: 10px; }

  .card {
    background: #fff; border-radius: 10px; padding: 14px 16px;
    border-left: 4px solid #ccc;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
  }
  .card.positive { border-left-color: #34c759; }
  .card.negative { border-left-color: #ff3b30; }
  .card.neutral  { border-left-color: #ff9500; }
  .card-meta {
    display: flex; gap: 6px; align-items: center;
    font-size: 11px; color: #888; margin-bottom: 6px; flex-wrap: wrap;
  }
  .badge {
    font-size: 10px; font-weight: 600; padding: 1px 6px;
    border-radius: 4px; text-transform: uppercase;
  }
  .badge.positive { background: #e8f9ee; color: #1a7a35; }
  .badge.negative { background: #ffeeed; color: #c0392b; }
  .badge.neutral  { background: #fff3e0; color: #b45309; }
  .badge.none     { background: #f0f0f0; color: #666; }
  .card-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; line-height: 1.4; }
  .card-title a { color: #1d1d1f; text-decoration: none; }
  .card-title a:hover { color: #0071e3; }
  .card-summary { font-size: 13px; color: #444; line-height: 1.5; margin-bottom: 6px; }
  .topics { display: flex; gap: 4px; flex-wrap: wrap; }
  .topic {
    font-size: 11px; background: #f0f0f0; color: #555;
    padding: 2px 7px; border-radius: 4px;
  }
  .no-articles { text-align: center; color: #999; padding: 60px 0; font-size: 14px; }
</style>
</head>
<body>

<header>
  <h1>📰 News Monitor — РИМ</h1>
  <div class="controls">
    <select id="source">
      <option value="google">Google News</option>
      <option value="sostav">Sostav.ru</option>
      <option value="adindex">AdIndex</option>
      <option value="dzen">Dzen.ru</option>
      <option value="all">Все источники</option>
    </select>
    <label class="cb-label"><input type="checkbox" id="skip-llm"> без LLM</label>
    <label class="cb-label"><input type="checkbox" id="skip-extract"> без текста</label>
    <button id="run-btn">▶ Запустить</button>
  </div>
  <div class="stats" id="stats">загрузка…</div>
</header>

<div class="layout">
  <div class="terminal-wrap">
    <div class="terminal-title">Лог запуска</div>
    <div id="terminal"><span style="color:#555">— ожидание запуска —</span></div>
  </div>
  <div class="articles-wrap">
    <h2 id="articles-title">Статьи в базе</h2>
    <div class="articles" id="articles">
      <div class="no-articles">загрузка…</div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);

// ── Utilities ────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day:'2-digit', month:'2-digit', year:'2-digit' })
    + ' ' + d.toLocaleTimeString('ru-RU', { hour:'2-digit', minute:'2-digit' });
}

function parseTopics(raw) {
  if (!raw) return [];
  try { return JSON.parse(raw); } catch { return []; }
}

function classifyLine(text) {
  const t = text.toLowerCase();
  if (t.includes('error') || t.includes('traceback') || t.includes('exception')) return 'line-err';
  if (t.includes('warning') || t.includes('warn')) return 'line-warn';
  if (t.includes('saved') || t.includes('results') || t.includes('===')) return 'line-ok';
  if (t.startsWith('2026') || t.includes(' info ') || t.includes(' debug ')) return 'line-info';
  if (t.startsWith('---') || t.startsWith('===')) return 'line-sep';
  return '';
}

// ── Render articles ───────────────────────────────────────
function renderArticles(articles) {
  const container = $('articles');
  if (!articles.length) {
    container.innerHTML = '<div class="no-articles">Нет статей в базе</div>';
    return;
  }
  $('articles-title').textContent = `Статьи в базе (${articles.length})`;
  container.innerHTML = articles.map(a => {
    const sent = a.ai_sentiment || 'none';
    const sentLabel = { positive:'позитив', negative:'негатив', neutral:'нейтрал', none:'—' }[sent] || sent;
    const topics = parseTopics(a.ai_topics);
    return `
    <div class="card ${sent}">
      <div class="card-meta">
        <span class="badge ${sent}">${sentLabel}</span>
        <span>${a.source || ''}</span>
        <span>${formatDate(a.created_at)}</span>
      </div>
      <div class="card-title"><a href="${a.url}" target="_blank">${a.title}</a></div>
      ${a.ai_summary ? `<div class="card-summary">${a.ai_summary}</div>` : ''}
      ${topics.length ? `<div class="topics">${topics.map(t=>`<span class="topic">${t}</span>`).join('')}</div>` : ''}
    </div>`;
  }).join('');
}

// ── Load articles + stats ─────────────────────────────────
async function loadArticles() {
  const [arts, stats] = await Promise.all([
    fetch('/api/articles').then(r => r.json()),
    fetch('/api/stats').then(r => r.json()),
  ]);
  renderArticles(arts);
  $('stats').textContent =
    `всего: ${stats.total}` +
    (stats.by_sentiment.positive ? ` · 🟢${stats.by_sentiment.positive}` : '') +
    (stats.by_sentiment.negative ? ` · 🔴${stats.by_sentiment.negative}` : '') +
    (stats.by_sentiment.neutral  ? ` · 🟡${stats.by_sentiment.neutral}`  : '');
}

// ── Run pipeline ──────────────────────────────────────────
$('run-btn').addEventListener('click', () => {
  const source    = $('source').value;
  const skipLlm   = $('skip-llm').checked;
  const skipEx    = $('skip-extract').checked;

  const btn = $('run-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Работает…';

  const term = $('terminal');
  term.innerHTML = '';

  const params = new URLSearchParams({ source });
  if (skipLlm) params.set('skip_llm', 'true');
  if (skipEx)  params.set('skip_extract', 'true');

  const es = new EventSource(`/api/run?${params}`);

  es.onmessage = e => {
    const text = JSON.parse(e.data);
    if (text === null) {
      es.close();
      btn.disabled = false;
      btn.textContent = '▶ Запустить';
      loadArticles();
      return;
    }
    const div = document.createElement('div');
    div.className = classifyLine(text);
    div.textContent = text;
    term.appendChild(div);
    term.scrollTop = term.scrollHeight;
  };

  es.onerror = () => {
    es.close();
    btn.disabled = false;
    btn.textContent = '▶ Запустить';
  };
});

// ── Init ──────────────────────────────────────────────────
loadArticles();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/api/articles")
def api_articles():
    return get_articles()


@app.get("/api/stats")
def api_stats():
    return get_stats()


@app.get("/api/run")
async def api_run(
    source: str = Query("google"),
    skip_llm: bool = Query(False),
    skip_extract: bool = Query(False),
):
    cmd = [sys.executable, "run_once.py", "--source", source]
    if skip_llm:
        cmd.append("--skip-llm")
    if skip_extract:
        cmd.append("--skip-extract")

    async def generate():
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            yield f"data: {json.dumps(line)}\n\n"
        await proc.wait()
        yield "data: null\n\n"  # signals completion to JS

    return StreamingResponse(generate(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
