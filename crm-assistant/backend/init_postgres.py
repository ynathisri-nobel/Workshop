"""
PostgreSQL Database Initialization Script
Migrates the SQLite schema to PostgreSQL on AWS RDS.

Usage:
    pip install psycopg2-binary
    python init_postgres.py
"""
import psycopg2
from psycopg2.extras import RealDictCursor

# --- RDS Connection Config ---
DB_CONFIG = {
    "host": "database-1.cav6m4s4mo5b.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": "nEGPFDsSOdsdTEEULZea",
    "sslmode": "require",
}

SCHEMA_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    department TEXT NOT NULL DEFAULT 'general',
    allowed_sensitivity INTEGER NOT NULL DEFAULT 1,
    can_input INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Entities (customers/partners)
CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'customer',
    industry TEXT,
    owner_department TEXT NOT NULL DEFAULT 'general',
    notes TEXT,
    registration_no TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Entity aliases (alternate names)
CREATE TABLE IF NOT EXISTS entity_aliases (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT NOT NULL DEFAULT 'other',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);

-- Contacts
CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    person_name TEXT NOT NULL,
    title TEXT,
    email TEXT,
    phone TEXT
);

-- Interactions (meeting notes)
CREATE TABLE IF NOT EXISTS interactions (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    meeting_date TEXT,
    our_attendees TEXT,
    their_attendees TEXT,
    summary TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Documents
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id) ON DELETE SET NULL,
    filename TEXT,
    filetype TEXT,
    sensitivity INTEGER NOT NULL DEFAULT 1,
    department TEXT NOT NULL DEFAULT 'general',
    uploaded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Knowledge chunks (RAG store)
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    interaction_id INTEGER REFERENCES interactions(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    fact_or_opinion TEXT NOT NULL DEFAULT 'fact',
    fo_confidence REAL DEFAULT 0.0,
    source_person TEXT,
    source_label TEXT,
    sensitivity INTEGER NOT NULL DEFAULT 1,
    department TEXT NOT NULL DEFAULT 'general',
    embedding TEXT,
    image_path TEXT,
    flagged INTEGER NOT NULL DEFAULT 0,
    flag_reason TEXT,
    flagged_by INTEGER REFERENCES users(id),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Issues
CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT DEFAULT 'medium',
    sensitivity INTEGER NOT NULL DEFAULT 1,
    department TEXT NOT NULL DEFAULT 'general',
    event_date TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    resolution TEXT,
    resolved_by INTEGER REFERENCES users(id)
);

-- Financials
CREATE TABLE IF NOT EXISTS financials (
    id SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    period TEXT,
    revenue REAL,
    net_profit REAL,
    currency TEXT DEFAULT 'THB',
    source_type TEXT NOT NULL DEFAULT 'internal',
    source TEXT,
    sensitivity INTEGER NOT NULL DEFAULT 2,
    department TEXT NOT NULL DEFAULT 'finance',
    created_at TIMESTAMP DEFAULT NOW()
);
"""

# Seed demo users (same as SQLite seed)
SEED_USERS = [
    ("admin", "admin123", "System Admin", "admin", "all", 3, 1),
    ("exec", "exec123", "คุณสมชาย (CEO)", "executive", "all", 3, 1),
    ("sales1", "sales123", "Napat (Sales Mgr)", "manager", "sales", 2, 1),
    ("viewer", "view123", "Junior Viewer", "viewer", "sales", 1, 0),
    ("fin1", "fin123", "Ratchada (Finance)", "manager", "finance", 3, 1),
]


def hash_password(password: str) -> str:
    """Hash password using bcrypt (same as app.auth)."""
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return ctx.hash(password)


def main():
    print(f"Connecting to PostgreSQL at {DB_CONFIG['host']}...")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create schema
    print("Creating tables...")
    cur.execute(SCHEMA_SQL)
    print("Schema created successfully.")

    # Seed users
    print("Seeding demo users...")
    for (username, password, full_name, role, department, sensitivity, can_input) in SEED_USERS:
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if not cur.fetchone():
            pw_hash = hash_password(password)
            cur.execute(
                """INSERT INTO users (username, password_hash, full_name, role, department, allowed_sensitivity, can_input)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (username, pw_hash, full_name, role, department, sensitivity, can_input)
            )
            print(f"  Created user: {username}")
        else:
            print(f"  User already exists: {username}")

    # Seed entities
    DEMO_ENTITIES = [
        ("Siam Cement Group", "customer", "Manufacturing", "sales", "ลูกค้ารายใหญ่ภาคการผลิต สนใจโซลูชัน ERP"),
        ("Bangkok Bank", "customer", "Banking", "sales", "Enterprise customer, interested in cloud migration"),
        ("AWS Thailand", "partner", "Cloud", "general", "Strategic cloud partner"),
        ("PTT Digital", "customer", "Energy", "finance", "โครงการ data platform งบประมาณสูง (confidential)"),
    ]

    print("Seeding entities...")
    for (name, etype, industry, dept, notes) in DEMO_ENTITIES:
        cur.execute("SELECT 1 FROM entities WHERE name = %s", (name,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO entities (name, type, industry, owner_department, notes) VALUES (%s, %s, %s, %s, %s)",
                (name, etype, industry, dept, notes)
            )
            print(f"  Created entity: {name}")
        else:
            print(f"  Entity already exists: {name}")

    cur.close()
    conn.close()
    print("\nDone! PostgreSQL database is ready.")


if __name__ == "__main__":
    main()
