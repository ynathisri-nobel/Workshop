"""Seed demo data: users (various roles/depts), entities, meetings, issues, financials.

Run:  ./.venv/bin/python -m app.seed
"""
from .db import db, init_db
from .auth import hash_password
from . import ingest


DEMO_USERS = [
    # username, password, full_name, role, department, allowed_sensitivity, can_input
    ("admin",  "admin123",  "System Admin",      "admin",     "all",     3, 1),
    ("exec",   "exec123",   "คุณสมชาย (CEO)",     "executive", "all",     3, 1),
    ("sales1", "sales123",  "Napat (Sales Mgr)", "manager",   "sales",   2, 1),
    ("viewer", "view123",   "Junior Viewer",     "viewer",    "sales",   1, 0),
    ("fin1",   "fin123",    "Ratchada (Finance)","manager",   "finance", 3, 1),
]

DEMO_ENTITIES = [
    # name, type, industry, owner_department, notes
    ("Siam Cement Group", "customer", "Manufacturing", "sales",
     "ลูกค้ารายใหญ่ภาคการผลิต สนใจโซลูชัน ERP"),
    ("Bangkok Bank",      "customer", "Banking",       "sales",
     "Enterprise customer, interested in cloud migration"),
    ("AWS Thailand",      "partner",  "Cloud",         "general",
     "Strategic cloud partner"),
    ("PTT Digital",       "customer", "Energy",        "finance",
     "โครงการ data platform งบประมาณสูง (confidential)"),
]

# entity_index -> list of (person_name, title)
DEMO_CONTACTS = {
    0: [("Khun Anucha", "CIO"), ("Khun Malee", "Procurement Lead")],
    1: [("Mr. Prasert", "Head of IT"), ("Ms. Wanida", "CFO")],
    2: [("John Carter", "Partner Manager")],
    3: [("Khun Direk", "VP Digital")],
}

# (entity_index, date, ours, theirs, summary, sensitivity, department)
DEMO_INTERACTIONS = [
    (0, "2026-06-10", "คุณสมชาย, Napat", "Khun Anucha",
     "ประชุมที่สำนักงานลูกค้า ลูกค้ายืนยันงบ 12 ล้านบาทสำหรับ ERP เฟสแรก (fact). "
     "คุณสมชายรู้สึกว่า CIO ค่อนข้างลังเลเรื่อง timeline และน่าจะอยากเลื่อนไป Q4 (opinion). "
     "ลูกค้าขอ POC ภายใน 30 วัน", 1, "sales"),
    (1, "2026-06-20", "Napat", "Mr. Prasert, Ms. Wanida",
     "Bangkok Bank confirmed they signed the cloud migration contract worth 8M THB (fact). "
     "The CFO seemed very positive and I believe they will expand to phase 2 next year (opinion). "
     "They raised a concern about data residency compliance.", 2, "sales"),
    (3, "2026-07-01", "คุณสมชาย, Ratchada", "Khun Direk",
     "PTT Digital data platform โครงการลับ งบ 45 ล้านบาท (restricted). "
     "ยังไม่ได้ข้อสรุปเรื่อง security architecture", 3, "finance"),
]

# (entity_index, title, description, priority, sensitivity, department)
DEMO_ISSUES = [
    (0, "POC ERP ยังไม่ส่งมอบ", "ลูกค้า SCG รอ POC ภายใน 30 วัน ทีมยังไม่เริ่ม", "high", 1, "sales"),
    (1, "Data residency compliance", "Bangkok Bank needs confirmation that data stays in-region", "high", 2, "sales"),
    (3, "Security architecture pending", "PTT Digital ยังไม่อนุมัติ security design", "medium", 3, "finance"),
]

# (entity_index, period, revenue, net_profit, currency, source_type, source, sensitivity, department)
DEMO_FINANCIALS = [
    (0, "FY2025", 250000.0, 30000.0, "MTHB", "internal", "internal-erp", 2, "finance"),
    (1, "FY2025", 180000.0, 45000.0, "MTHB", "internal", "internal-erp", 2, "finance"),
    (3, "FY2025", 500000.0, 60000.0, "MTHB", "internal", "internal-erp", 3, "finance"),
]


def run():
    init_db()
    with db() as conn:
        # users
        for u in DEMO_USERS:
            exists = conn.execute("SELECT 1 FROM users WHERE username=?", (u[0],)).fetchone()
            if not exists:
                conn.execute(
                    """INSERT INTO users (username,password_hash,full_name,role,department,allowed_sensitivity,can_input)
                       VALUES (?,?,?,?,?,?,?)""",
                    (u[0], hash_password(u[1]), u[2], u[3], u[4], u[5], u[6]))
        # entities
        entity_ids = []
        for e in DEMO_ENTITIES:
            row = conn.execute("SELECT id FROM entities WHERE name=?", (e[0],)).fetchone()
            if row:
                entity_ids.append(row["id"]); continue
            cur = conn.execute(
                "INSERT INTO entities (name,type,industry,owner_department,notes) VALUES (?,?,?,?,?)", e)
            entity_ids.append(cur.lastrowid)
        # contacts
        for idx, contacts in DEMO_CONTACTS.items():
            for (nm, title) in contacts:
                dup = conn.execute("SELECT 1 FROM contacts WHERE entity_id=? AND person_name=?",
                                   (entity_ids[idx], nm)).fetchone()
                if not dup:
                    conn.execute("INSERT INTO contacts (entity_id,person_name,title) VALUES (?,?,?)",
                                 (entity_ids[idx], nm, title))
        # financials
        for f in DEMO_FINANCIALS:
            eid = entity_ids[f[0]]
            dup = conn.execute("SELECT 1 FROM financials WHERE entity_id=? AND period=?",
                               (eid, f[1])).fetchone()
            if not dup:
                conn.execute(
                    """INSERT INTO financials (entity_id,period,revenue,net_profit,currency,source_type,source,sensitivity,department)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (eid, f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8]))

    # Determine if we already ingested (avoid duplicate embeddings on re-run)
    with db() as conn:
        already = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
    if already:
        print(f"Chunks already present ({already}); skipping interaction/issue ingestion.")
        print("Seed complete.")
        return

    # interactions (ingested with embeddings + auto fact/opinion)
    for (idx, date, ours, theirs, summary, sens, dept) in DEMO_INTERACTIONS:
        eid = entity_ids[idx]
        with db() as conn:
            cur = conn.execute(
                """INSERT INTO interactions (entity_id,meeting_date,our_attendees,their_attendees,summary)
                   VALUES (?,?,?,?,?)""", (eid, date, ours, theirs, summary))
            iid = cur.lastrowid
        meta = f"Meeting {date} | ours: {ours} | theirs: {theirs}"
        ingest.ingest_chunks(ingest.chunk_text(f"{meta}\n{summary}"),
                             entity_id=eid, interaction_id=iid, sensitivity=sens,
                             department=dept, source_label=f"meeting:{date}")
        print(f"  ingested meeting for entity {eid}")

    # issues
    for (idx, title, desc, pri, sens, dept) in DEMO_ISSUES:
        eid = entity_ids[idx]
        with db() as conn:
            conn.execute(
                """INSERT INTO issues (entity_id,title,description,priority,sensitivity,department)
                   VALUES (?,?,?,?,?,?)""", (eid, title, desc, pri, sens, dept))
        ingest.ingest_chunks([f"OPEN ISSUE: {title}. {desc} (priority {pri})"],
                             entity_id=eid, sensitivity=sens, department=dept,
                             source_label="issue", default_label="fact")
        print(f"  ingested issue '{title}'")

    print("Seed complete.")


if __name__ == "__main__":
    run()
