"""Mock partner usage data: 1 partner entity + ~20 example "transactions"
(meetings / issues / notes), ingested through the normal pipeline so they are
searchable, editable in the Manage tab, and usable by the chat/RAG.

Run:  ./.venv/bin/python -m app.mock_partner

Idempotent: if the partner already has chunks, ingestion is skipped.
Requires AWS Bedrock access (for embeddings + fact/opinion classification),
same as the normal ingest flow.
"""
from .db import db, init_db
from . import ingest


PARTNER = {
    "name": "Microsoft Thailand",
    "type": "partner",
    "industry": "Cloud / IT",
    "owner_department": "general",
    "notes": "Strategic cloud & licensing partner (mockup data for demo/usage examples)",
}

CONTACTS = [
    ("Khun Siriporn", "Partner Account Manager"),
    ("Mr. David Lim", "Cloud Solutions Architect"),
    ("Khun Thanaporn", "Channel Sales Lead"),
]

# Each transaction:
#   kind: "meeting" | "issue" | "note"
#   date, reporter (username), text, sensitivity, department
#   ours/theirs: for meetings; priority: for issues
TRANSACTIONS = [
    {"kind": "meeting", "date": "2026-01-15", "reporter": "sales1", "sens": 1, "dept": "sales",
     "ours": "Napat", "theirs": "Khun Siriporn",
     "text": "Partner onboarding kickoff. เซ็นสัญญา reseller agreement เรียบร้อย ตั้งเป้า co-sell pipeline 20 ล้านบาทสำหรับปี 2026 (fact). Napat รู้สึกว่าทีมพาร์ทเนอร์ committed และตอบสนองเร็วมาก (opinion)."},
    {"kind": "note", "date": "2026-01-22", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "เปิดสิทธิ์ partner portal ให้วิศวกรของเรา 5 คน และเปิดใช้งาน deal registration เรียบร้อย."},
    {"kind": "meeting", "date": "2026-02-05", "reporter": "exec", "sens": 1, "dept": "general",
     "ours": "คุณสมชาย (CEO)", "theirs": "Mr. David Lim",
     "text": "QBR review Q4 2025. พาร์ทเนอร์แจ้งว่าเราได้เลื่อนระดับเป็น Gold tier แล้ว (fact). CEO เชื่อว่าการอัปเกรด tier จะช่วยให้ได้ margin ที่ดีขึ้น (opinion)."},
    {"kind": "note", "date": "2026-02-12", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "ลงทะเบียน co-sell opportunity: โครงการ cloud migration ของ Bangkok Bank มูลค่าประมาณ 8 ล้านบาท พาร์ทเนอร์สนับสนุน Azure credits."},
    {"kind": "note", "date": "2026-02-20", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "จัด joint webinar หัวข้อ 'Cloud for Banking' ร่วมกับพาร์ทเนอร์ มีผู้ลงทะเบียน 120 คน ได้ qualified leads 15 ราย."},
    {"kind": "note", "date": "2026-03-01", "reporter": "fin1", "sens": 1, "dept": "finance",
     "text": "คำขอ MDF (Marketing Development Fund) จำนวน 500,000 บาท ได้รับอนุมัติจากพาร์ทเนอร์สำหรับแคมเปญ Q1."},
    {"kind": "issue", "date": "2026-03-08", "reporter": "sales1", "sens": 1, "dept": "sales", "priority": "high",
     "text": "การ provision license ล่าช้า 2 สัปดาห์สำหรับโครงการ PTT Digital ทำให้เริ่ม POC ไม่ได้."},
    {"kind": "meeting", "date": "2026-03-15", "reporter": "sales1", "sens": 1, "dept": "sales",
     "ours": "Napat", "theirs": "Khun Thanaporn",
     "text": "ปิดดีลได้: โครงการย้าย ERP ของ SCG ขึ้น Azure มูลค่าสัญญา 12 ล้านบาท (fact). พาร์ทเนอร์ช่วยด้าน solution architecture."},
    {"kind": "note", "date": "2026-03-22", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "วิศวกรของเรา 5 คนสอบผ่าน Azure Solutions Architect certification (AZ-305)."},
    {"kind": "note", "date": "2026-04-02", "reporter": "fin1", "sens": 2, "dept": "finance",
     "text": "ได้รับ rebate ไตรมาส 1 จำนวน 350,000 บาทจากพาร์ทเนอร์ คำนวณจากยอดขาย 4.2 ล้านบาท (confidential)."},
    {"kind": "meeting", "date": "2026-04-10", "reporter": "exec", "sens": 1, "dept": "general",
     "ours": "คุณสมชาย (CEO)", "theirs": "Khun Siriporn",
     "text": "ประชุม executive sponsor. พาร์ทเนอร์ยืนยันจัดสรร dedicated technical resource ให้ (fact). CEO มองว่าความสัมพันธ์แน่นแฟ้นขึ้นเรื่อยๆ (opinion)."},
    {"kind": "note", "date": "2026-04-18", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "รับ briefing ผลิตภัณฑ์ใหม่กลุ่ม Copilot จากพาร์ทเนอร์ ระบุโอกาส upsell ได้ 3 ราย."},
    {"kind": "issue", "date": "2026-04-25", "reporter": "sales1", "sens": 1, "dept": "sales", "priority": "medium",
     "text": "พาร์ทเนอร์ตอบ support ticket ระดับ P2 ช้า 5 วัน เกิน SLA ที่กำหนดไว้ 2 วัน (SLA breach)."},
    {"kind": "note", "date": "2026-05-03", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "เริ่ม joint POC ด้าน data analytics platform ร่วมกับ Bangkok Bank และพาร์ทเนอร์."},
    {"kind": "meeting", "date": "2026-05-12", "reporter": "sales1", "sens": 2, "dept": "sales",
     "ours": "Napat", "theirs": "Khun Thanaporn",
     "text": "เจรจาราคา ได้ส่วนลดพาร์ทเนอร์เพิ่มอีก 8% สำหรับดีลระดับ enterprise (fact, confidential)."},
    {"kind": "note", "date": "2026-05-20", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "พาร์ทเนอร์จัด training ให้ทีม pre-sales ของเรา มีผู้เข้าร่วม 12 คน."},
    {"kind": "note", "date": "2026-06-01", "reporter": "fin1", "sens": 2, "dept": "finance",
     "text": "ต่อสัญญาปี 2026-2027 พร้อมโครงสร้าง rebate ที่ดีขึ้น (confidential)."},
    {"kind": "note", "date": "2026-06-10", "reporter": "exec", "sens": 3, "dept": "general",
     "text": "Roadmap alignment: พาร์ทเนอร์แชร์ product roadmap ครึ่งปีหลัง 2026 ภายใต้ NDA (restricted)."},
    {"kind": "issue", "date": "2026-06-18", "reporter": "sales1", "sens": 1, "dept": "sales", "priority": "low",
     "text": "การอนุมัติ deal registration สำหรับส่วนขยายของ PTT ค้างอยู่ที่พาร์ทเนอร์เกิน 3 สัปดาห์."},
    {"kind": "meeting", "date": "2026-06-28", "reporter": "exec", "sens": 1, "dept": "general",
     "ours": "คุณสมชาย (CEO)", "theirs": "Mr. David Lim",
     "text": "QBR Q2 2026. ทำได้ 62% ของเป้า pipeline ทั้งปี (fact). CEO มองบวกอย่างระมัดระวังว่าจะถึงเป้าทั้งปี (opinion)."},
]


def _user_ids(conn):
    rows = conn.execute("SELECT id, username FROM users").fetchall()
    return {r["username"]: r["id"] for r in rows}


def run():
    init_db()
    with db() as conn:
        # entity (partner)
        row = conn.execute("SELECT id FROM entities WHERE name=?", (PARTNER["name"],)).fetchone()
        if row:
            entity_id = row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO entities (name,type,industry,owner_department,notes) VALUES (?,?,?,?,?)",
                (PARTNER["name"], PARTNER["type"], PARTNER["industry"],
                 PARTNER["owner_department"], PARTNER["notes"]))
            entity_id = cur.lastrowid

        # contacts
        for (nm, title) in CONTACTS:
            dup = conn.execute("SELECT 1 FROM contacts WHERE entity_id=? AND person_name=?",
                               (entity_id, nm)).fetchone()
            if not dup:
                conn.execute("INSERT INTO contacts (entity_id,person_name,title) VALUES (?,?,?)",
                             (entity_id, nm, title))

        users = _user_ids(conn)
        existing = conn.execute(
            "SELECT COUNT(*) c FROM chunks WHERE entity_id=?", (entity_id,)).fetchone()["c"]

    if existing:
        print(f"Partner '{PARTNER['name']}' already has {existing} chunks; skipping ingestion.")
        return

    print(f"Ingesting {len(TRANSACTIONS)} transactions for partner '{PARTNER['name']}' (id={entity_id})...")
    for i, t in enumerate(TRANSACTIONS, 1):
        created_by = users.get(t["reporter"])
        interaction_id = None

        if t["kind"] == "meeting":
            with db() as conn:
                cur = conn.execute(
                    """INSERT INTO interactions (entity_id,meeting_date,our_attendees,their_attendees,summary,created_by)
                       VALUES (?,?,?,?,?,?)""",
                    (entity_id, t["date"], t.get("ours", ""), t.get("theirs", ""), t["text"], created_by))
                interaction_id = cur.lastrowid
            meta = f"Meeting {t['date']} | ours: {t.get('ours','')} | theirs: {t.get('theirs','')}"
            body = f"{meta}\n{t['text']}"
            source_label = f"meeting:{t['date']}"
            ingest.ingest_chunks(ingest.chunk_text(body), entity_id=entity_id,
                                 interaction_id=interaction_id, sensitivity=t["sens"],
                                 department=t["dept"], source_label=source_label,
                                 created_by=created_by)

        elif t["kind"] == "issue":
            with db() as conn:
                conn.execute(
                    """INSERT INTO issues (entity_id,title,description,priority,sensitivity,department,created_by)
                       VALUES (?,?,?,?,?,?,?)""",
                    (entity_id, t["text"][:60], t["text"], t.get("priority", "medium"),
                     t["sens"], t["dept"], created_by))
            ingest.ingest_chunks([f"OPEN ISSUE ({t['date']}): {t['text']} (priority {t.get('priority','medium')})"],
                                 entity_id=entity_id, sensitivity=t["sens"], department=t["dept"],
                                 source_label="issue", created_by=created_by, default_label="fact")

        else:  # note
            ingest.ingest_chunks([f"NOTE ({t['date']}): {t['text']}"],
                                 entity_id=entity_id, sensitivity=t["sens"], department=t["dept"],
                                 source_label=f"note:{t['date']}", created_by=created_by)

        print(f"  [{i}/{len(TRANSACTIONS)}] {t['kind']} · {t['date']} · by {t['reporter']}")

    print("Mock partner data complete.")


if __name__ == "__main__":
    run()
