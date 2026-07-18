"""Seed SCG social data that was skipped."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.db import db, init_db
from app import ingest

init_db()

with db() as conn:
    row = conn.execute("SELECT id FROM entities WHERE name='Siam Cement Group'").fetchone()
    eid = row["id"]
    uid = conn.execute("SELECT id FROM users WHERE username='sales1'").fetchone()["id"]

DATA = [
    {"kind": "note", "date": "2026-01-28",
     "text": "ส่งกระเช้าปีใหม่ให้ คุณวิชัย (CTO ของ SCG): กระเช้า Jim Thompson + ไวน์ Opus One 1 ขวด มูลค่า ~18,000 บาท คุณวิชัยโทรมาขอบคุณเอง บอกว่าประทับใจมาก"},
    {"kind": "meeting", "date": "2026-03-20",
     "ours": "Napat", "theirs": "คุณวิชัย, คุณสมหญิง",
     "text": "เลี้ยงอาหารญี่ปุ่นที่ร้าน Sushi Masato (ทองหล่อ) คุยเรื่อง phase 2 ของ cloud migration คุณวิชัยบอกว่าอยากขยาย scope เพิ่ม data analytics (fact) แต่ยังต้องขออนุมัติบอร์ดก่อน (fact). Napat รู้สึกว่าดีลนี้น่าจะปิดได้ภายใน Q2 (opinion). ค่าอาหาร ~9,500 บาท (3 คน)"},
    {"kind": "note", "date": "2026-05-15",
     "text": "จัดทริป team building ร่วมกับทีม IT ของ SCG: ล่องเรือดินเนอร์แม่น้ำเจ้าพระยา (Grand Pearl) 12 คน ค่าใช้จ่าย ~36,000 บาท บรรยากาศดี ทำให้ relationship แน่นขึ้น คุณสมหญิงบอกจะช่วย intro ให้รู้จักทีม procurement"},
    {"kind": "note", "date": "2026-07-01",
     "text": "สรุป preferences ผู้ติดต่อ SCG: คุณวิชัย (CTO) ชอบอาหารญี่ปุ่น โดยเฉพาะ omakase, ดื่มสาเก. ชอบไวน์ฝรั่งเศส (Bordeaux). คุณสมหญิง ชอบกิจกรรมกลุ่ม/team building. งบเลี้ยงรับรองปกติ 8,000-20,000 บาท/ครั้ง"},
]

for i, item in enumerate(DATA, 1):
    if item["kind"] == "meeting":
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO interactions (entity_id,meeting_date,our_attendees,their_attendees,summary,created_by) VALUES (?,?,?,?,?,?)",
                (eid, item["date"], item.get("ours", ""), item.get("theirs", ""), item["text"], uid))
            iid = cur.lastrowid
        meta = f"Meeting {item['date']} | ours: {item.get('ours','')} | theirs: {item.get('theirs','')}"
        body = f"{meta}\n{item['text']}"
        ingest.ingest_chunks(ingest.chunk_text(body), entity_id=eid, interaction_id=iid,
                             sensitivity=1, department="sales",
                             source_label=f"meeting:{item['date']}", created_by=uid)
    else:
        ingest.ingest_chunks([f"NOTE ({item['date']}): {item['text']}"],
                             entity_id=eid, sensitivity=1, department="sales",
                             source_label=f"note:{item['date']}", created_by=uid)
    print(f"  [{i}/{len(DATA)}] {item['kind']} - SCG - {item['date']}")

print("SCG social data complete!")
