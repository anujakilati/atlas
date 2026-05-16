import sqlite3
from pathlib import Path
from typing import Dict, Any

def init_db(db_path: str):
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        label TEXT,
        score REAL,
        bbox TEXT,
        frame_path TEXT,
        clip_path TEXT,
        meta TEXT
    )
    ''')
    conn.commit()
    conn.close()

def insert_event(db_path: str, event: Dict[str, Any]):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, label TEXT, score REAL, bbox TEXT,
        frame_path TEXT, clip_path TEXT, meta TEXT
    )''')
    cur.execute('''INSERT INTO events (ts,label,score,bbox,frame_path,clip_path,meta)
    VALUES (?,?,?,?,?,?,?)''', (
        event.get("ts"), event.get("label"), event.get("score"), str(event.get("bbox")), event.get("frame_path"), event.get("clip_path"), str(event.get("meta"))
    ))
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid

def list_events(db_path: str, limit: int = 100):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL, label TEXT, score REAL, bbox TEXT,
        frame_path TEXT, clip_path TEXT, meta TEXT
    )''')
    cur.execute('SELECT id, ts, label, score, bbox, frame_path, clip_path, meta FROM events ORDER BY ts DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows
