"""SQLite persistence for NEXUS. Local-only; no payment credentials are stored."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get('NEXUS_DB_PATH', str(Path(__file__).resolve().parent.parent / 'data.db')))
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1, interval_sec INTEGER NOT NULL DEFAULT 60
);
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, recipient TEXT, postal TEXT,
    address TEXT, phone TEXT, email TEXT, payment_label TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY, group_name TEXT NOT NULL DEFAULT 'default',
    site_key TEXT NOT NULL REFERENCES sites(key), product_url TEXT, keyword TEXT,
    qty INTEGER NOT NULL DEFAULT 1, profile_id INTEGER REFERENCES profiles(id),
    mode TEXT NOT NULL DEFAULT 'monitor', status TEXT NOT NULL DEFAULT 'idle',
    status_msg TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY, task_id INTEGER, ts TEXT NOT NULL, level TEXT NOT NULL, msg TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_task_id ON logs(task_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS idx_tasks_site ON tasks(site_key);
"""
DEFAULT_SITES = [
    ('amazon','Amazon'),('rakuten','楽天ブックス'),('yahoo','Yahoo!ショッピング'),
    ('pokecenter','ポケモンセンター'),('geo','GEO'),('joshin','Joshin'),
    ('amenity','アメニティードリーム'),('7net','セブンネット'),
]

def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')

@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c = sqlite3.connect(DB_PATH,timeout=10)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=5000')
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def init():
    with conn() as c:
        c.executescript(SCHEMA)
        for key,name in DEFAULT_SITES:
            c.execute('INSERT OR IGNORE INTO sites(key,name) VALUES (?,?)',(key,name))
        c.execute("UPDATE tasks SET status='stopped',status_msg='アプリ再起動により停止',updated_at=? WHERE status IN ('watching','queued')",(now(),))
        if os.getenv('NEXUS_SEED_DEMO') == '1' and not c.execute('SELECT 1 FROM tasks LIMIT 1').fetchone():
            examples = [
                ('Collectibles','pokecenter','ポケモンカード 新作BOX',1),
                ('Gaming','geo','Nintendo Switch 2',1),
                ('Hardware','amazon','GeForce RTX 5090',1),
                ('Gaming','joshin','PlayStation 5 Pro',1),
                ('Collectibles','rakuten','トレーディングカード 限定商品',2),
                ('Collectibles','yahoo','ワンピースカード BOX',1),
            ]
            for group,site,keyword,qty in examples:
                c.execute("INSERT INTO tasks(group_name,site_key,product_url,keyword,qty,mode,status,status_msg,updated_at) VALUES(?,?,'',?,?,'monitor','idle','サンプル / 未開始',?)",(group,site,keyword,qty,now()))

def log(task_id,level,msg):
    # Bound history for long-running operations.
    with conn() as c:
        c.execute('INSERT INTO logs(task_id,ts,level,msg) VALUES (?,?,?,?)',(task_id,now(),level,str(msg)[:1500]))
        # Per-write prune only when size crosses threshold (amortized).
        n=c.execute('SELECT MAX(id) FROM logs').fetchone()[0] or 0
        if n % 250 == 0:
            c.execute('DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 10000)')

def set_status(task_id,status,msg=None):
    with conn() as c:
        c.execute('UPDATE tasks SET status=?,status_msg=?,updated_at=? WHERE id=?',(status,str(msg or '')[:400],now(),task_id))

def dashboard():
    with conn() as c:
        tasks=[dict(r) for r in c.execute('''SELECT t.*,s.name AS site_name,p.name AS profile_name
            FROM tasks t JOIN sites s ON t.site_key=s.key LEFT JOIN profiles p ON p.id=t.profile_id
            ORDER BY t.id DESC''')]
        sites=[dict(r) for r in c.execute('SELECT * FROM sites ORDER BY id')]
        profiles=[dict(r) for r in c.execute('SELECT * FROM profiles ORDER BY id DESC')]
        logs=[dict(r) for r in c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 100')]
        today=c.execute("SELECT COUNT(*) FROM logs WHERE level='success' AND substr(ts,1,10)=?",(now()[:10],)).fetchone()[0]
    return {'tasks':tasks,'sites':sites,'profiles':profiles,'logs':logs,'success_today':today}
