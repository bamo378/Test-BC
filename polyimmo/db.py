"""Private application data; SQLite lives outside static assets and Git."""
import os
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, imported_at TEXT NOT NULL, kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
 source_id TEXT PRIMARY KEY REFERENCES sources(id), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invoices (
 source_id TEXT REFERENCES sources(id), row_number INTEGER, year INTEGER,
 quarter INTEGER, label TEXT, high_kwh REAL, low_kwh REAL,
 revenue_chf REAL, other_chf REAL, note TEXT,
 PRIMARY KEY(source_id,row_number)
);
CREATE TABLE IF NOT EXISTS grid_archive (
 source_id TEXT REFERENCES sources(id), row_number INTEGER,
 timestamp_local TEXT, kwh REAL,
 PRIMARY KEY(source_id,row_number)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements (
 plant_id TEXT NOT NULL, device_id TEXT NOT NULL, metric TEXT NOT NULL,
 start_utc TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
 value REAL NOT NULL, unit TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 PRIMARY KEY(plant_id,device_id,metric,start_utc,interval_seconds)
);
CREATE TABLE IF NOT EXISTS measurement_revisions (
 id INTEGER PRIMARY KEY, plant_id TEXT, device_id TEXT, metric TEXT,
 start_utc TEXT, interval_seconds INTEGER, old_value REAL, new_value REAL,
 changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_runs (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 status TEXT NOT NULL, error_code TEXT, points INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS portal_latest (
 plant_id TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenarios (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL,
 source_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manual_records (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, period_start TEXT NOT NULL,
 period_end TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS manual_expenses (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, expense_date TEXT NOT NULL,
 fingerprint TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS financial_revisions (
 id INTEGER PRIMARY KEY, record_type TEXT NOT NULL, record_id TEXT NOT NULL,
 action TEXT NOT NULL, old_payload TEXT, new_payload TEXT, changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history_imports (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 from_day TEXT NOT NULL, to_day TEXT NOT NULL, status TEXT NOT NULL,
 payload TEXT
);
"""


def connect(path=None):
    path = Path(path or os.environ.get('POLYIMMO_DB', '.local/polyimmo.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Create with restrictive permissions from the outset.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db
