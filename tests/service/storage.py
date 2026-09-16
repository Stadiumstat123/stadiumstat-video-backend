import os
import sqlite3
from pathlib import Path

ROOT = Path(os.environ.get('DATA_DIR', '/data'))

def connect():
    ROOT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ROOT / 'jobs.sqlite3', timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript('''CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL,
      config TEXT NOT NULL, bytes INTEGER NOT NULL DEFAULT 0, video_hash TEXT,
      progress INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
      result TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS job_owner_time ON jobs(owner, created_at);
      CREATE TABLE IF NOT EXISTS runtime (id INTEGER PRIMARY KEY, heartbeat INTEGER NOT NULL, ready INTEGER NOT NULL);
    ''')
    return con


def update(job, **values):
    import time
    values['updated_at'] = int(time.time())
    with connect() as db:
        db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?', [*values.values(), job])
