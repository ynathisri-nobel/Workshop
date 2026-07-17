"""SQLite database layer and schema."""
import sqlite3
import json
from contextlib import contextmanager
from . import config


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    -- role: admin | executive | manager | viewer
    role TEXT NOT NULL DEFAULT 'viewer',
    -- department the user belongs to; 'all' means cross-department (exec/admin)
    department TEXT NOT NULL DEFAULT 'general',
    -- max sensitivity level this user may READ (output side): 1..3
    allowed_sensitivity INTEGER NOT NULL DEFAULT 1,
    -- whether the user may WRITE/ingest data (input side)
    can_input INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    -- customer | partner
    type TEXT NOT NULL DEFAULT 'customer',
    industry TEXT,
    owner_department TEXT NOT NULL DEFAULT 'general',
    notes TEXT,
    -- juristic person / company registration number (strongest identity anchor)
    registration_no TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Alternative identifiers for an entity. The entity's IDENTITY is entities.id
-- (immutable); every name/label — internal short name, Thai name, English name,
-- former names after a rename, ticker, registration no — maps back to that id so a
-- company stays the same company even after it changes its name.
CREATE TABLE IF NOT EXISTS entity_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    -- short | th | en | former | ticker | registration | other
    alias_type TEXT NOT NULL DEFAULT 'other',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    person_name TEXT NOT NULL,
    title TEXT,
    email TEXT,
    phone TEXT
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    meeting_date TEXT,
    our_attendees TEXT,
    their_attendees TEXT,
    summary TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    filename TEXT,
    filetype TEXT,
    sensitivity INTEGER NOT NULL DEFAULT 1,
    department TEXT NOT NULL DEFAULT 'general',
    uploaded_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

-- The unified knowledge store used for retrieval.
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    interaction_id INTEGER REFERENCES interactions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    -- 'fact' | 'opinion' | 'mixed'
    fact_or_opinion TEXT NOT NULL DEFAULT 'fact',
    fo_confidence REAL DEFAULT 0.0,
    source_person TEXT,           -- whose statement/opinion this is
    source_label TEXT,            -- human readable source (file / meeting)
    sensitivity INTEGER NOT NULL DEFAULT 1,
    department TEXT NOT NULL DEFAULT 'general',
    embedding TEXT,               -- JSON array of floats
    image_path TEXT,              -- optional attached image (relative to UPLOAD_DIR)
    flagged INTEGER NOT NULL DEFAULT 0,   -- reported as incorrect
    flag_reason TEXT,
    flagged_by INTEGER REFERENCES users(id),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    -- open | resolved
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT DEFAULT 'medium',
    sensitivity INTEGER NOT NULL DEFAULT 1,
    department TEXT NOT NULL DEFAULT 'general',
    event_date TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT,
    resolution TEXT,
    resolved_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    period TEXT,                  -- e.g. FY2025, Q1-2026
    revenue REAL,
    net_profit REAL,
    currency TEXT DEFAULT 'THB',
    -- internal | external
    source_type TEXT NOT NULL DEFAULT 'internal',
    source TEXT,
    sensitivity INTEGER NOT NULL DEFAULT 2,
    department TEXT NOT NULL DEFAULT 'finance',
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def _ensure_columns(conn):
    """Lightweight migration: add columns that may be missing on older DBs."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(chunks)").fetchall()}
    for name, ddl in [
        ("flagged", "INTEGER NOT NULL DEFAULT 0"),
        ("flag_reason", "TEXT"),
        ("flagged_by", "INTEGER"),
        ("image_path", "TEXT"),
    ]:
        if name not in cols:
            conn.execute(f"ALTER TABLE chunks ADD COLUMN {name} {ddl}")
    # entities: multi-identifier support
    ent_cols = {r["name"] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
    if "registration_no" not in ent_cols:
        conn.execute("ALTER TABLE entities ADD COLUMN registration_no TEXT")
    # issues: resolution note + who resolved
    iss_cols = {r["name"] for r in conn.execute("PRAGMA table_info(issues)").fetchall()}
    if "resolution" not in iss_cols:
        conn.execute("ALTER TABLE issues ADD COLUMN resolution TEXT")
    if "resolved_by" not in iss_cols:
        conn.execute("ALTER TABLE issues ADD COLUMN resolved_by INTEGER")
    if "event_date" not in iss_cols:
        conn.execute("ALTER TABLE issues ADD COLUMN event_date TEXT")


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)


def dumps_vec(vec):
    return json.dumps([round(float(x), 6) for x in vec])


def loads_vec(s):
    if not s:
        return None
    return json.loads(s)
