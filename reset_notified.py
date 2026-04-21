import sqlite3

conn = sqlite3.connect("news_monitor.db")
conn.execute("UPDATE news SET notified = 0 WHERE filter_status = 'saved' OR filter_status IS NULL")
conn.commit()
count = conn.execute("SELECT COUNT(*) FROM news WHERE notified = 0").fetchone()[0]
print(f"Reset done. Ready to post: {count} articles")
conn.close()
