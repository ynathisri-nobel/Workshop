"""Seed social/entertainment mock data: restaurant meetings, gifts, team building."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import db, init_db
from app import ingest

init_db()

with db() as conn:
    entities = {r['name']: r['id'] for r in conn.execute('SELECT id, name FROM entities').fetchall()}
    users = {r['username']: r['id'] for r in conn.execute('SELECT id, username FROM users').fetchall()}

print('Entities:', list(entities.keys()))

SOCIAL_DATA = [
    # Microsoft Thailand
    {"entity": "Microsoft Thailand", "kind": "meeting", "date": "2026-02-14", "reporter": "sales1", "sens": 1, "dept": "sales",
     "ours": "Napat, คุณวิภา", "theirs": "Khun Siriporn, Mr. David Lim",
     "text": "เลี้ยงอาหารค่ำที่ร้าน Gaggan Anand (สุขุมวิท) เนื่องในโอกาสเซ็นสัญญา Gold Partner สำเร็จ บรรยากาศดีมาก คุณ Siriporn ชอบอาหาร Indian molecular gastronomy มาก (opinion). ค่าอาหาร ~15,000 บาท (4 คน) เบิกจ่ายจากงบ entertainment."},
    {"entity": "Microsoft Thailand", "kind": "note", "date": "2026-04-05", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "ส่งของขวัญวันสงกรานต์ให้ทีม Microsoft Thailand: ชุดกระเช้าผลไม้พรีเมียม + น้ำหอม Jo Malone 3 ชุด สำหรับ Khun Siriporn, Mr. David Lim, Khun Thanaporn มูลค่ารวม ~12,000 บาท"},
    {"entity": "Microsoft Thailand", "kind": "note", "date": "2026-05-28", "reporter": "exec", "sens": 2, "dept": "general",
     "text": "CEO เลี้ยงกอล์ฟ Mr. David Lim ที่ Alpine Golf Club คุยเรื่อง roadmap ครึ่งปีหลังแบบ informal ได้ insight เรื่อง AI Copilot pricing ที่ยังไม่ประกาศ (restricted). ค่า green fee + อาหาร ~8,000 บาท"},
    {"entity": "Microsoft Thailand", "kind": "meeting", "date": "2026-06-20", "reporter": "exec", "sens": 1, "dept": "general",
     "ours": "Napat, คุณสมชาย (CEO)", "theirs": "Khun Siriporn, Khun Thanaporn",
     "text": "เลี้ยงอาหารกลางวันที่ร้าน Suhring (สาทร) ฉลองปิดดีล SCG Azure migration 12 ล้านบาท Khun Siriporn ชอบ German fine dining มาก บอกว่าจะแนะนำเราให้ลูกค้าใหม่ 2 ราย (fact). ค่าอาหาร ~22,000 บาท (4 คน)"},

    # SCG (full name: Siam Cement Group)
    {"entity": "Siam Cement Group", "kind": "note", "date": "2026-01-28", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "ส่งกระเช้าปีใหม่ให้ คุณวิชัย (CTO ของ SCG): กระเช้า Jim Thompson + ไวน์ Opus One 1 ขวด มูลค่า ~18,000 บาท คุณวิชัยโทรมาขอบคุณเอง บอกว่าประทับใจมาก"},
    {"entity": "Siam Cement Group", "kind": "meeting", "date": "2026-03-20", "reporter": "sales1", "sens": 1, "dept": "sales",
     "ours": "Napat", "theirs": "คุณวิชัย, คุณสมหญิง",
     "text": "เลี้ยงอาหารญี่ปุ่นที่ร้าน Sushi Masato (ทองหล่อ) คุยเรื่อง phase 2 ของ cloud migration คุณวิชัยบอกว่าอยากขยาย scope เพิ่ม data analytics (fact) แต่ยังต้องขออนุมัติบอร์ดก่อน (fact). Napat รู้สึกว่าดีลนี้น่าจะปิดได้ภายใน Q2 (opinion). ค่าอาหาร ~9,500 บาท (3 คน)"},
    {"entity": "Siam Cement Group", "kind": "note", "date": "2026-05-15", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "จัดทริป team building ร่วมกับทีม IT ของ SCG: ล่องเรือดินเนอร์แม่น้ำเจ้าพระยา (Grand Pearl) 12 คน ค่าใช้จ่าย ~36,000 บาท บรรยากาศดี ทำให้ relationship แน่นขึ้น คุณสมหญิงบอกจะช่วย intro ให้รู้จักทีม procurement"},

    # Bangkok Bank
    {"entity": "Bangkok Bank", "kind": "meeting", "date": "2026-02-28", "reporter": "sales1", "sens": 1, "dept": "sales",
     "ours": "Napat, คุณวิภา", "theirs": "คุณประยุทธ์ (VP IT), คุณนภา",
     "text": "เลี้ยงอาหารที่ร้าน Le Normandie (Mandarin Oriental) เนื่องในโอกาสเริ่ม POC data analytics platform คุณประยุทธ์ชอบ French cuisine มาก เป็นร้านประจำ (opinion). คุยเรื่อง timeline POC 3 เดือน + budget approval process (fact). ค่าอาหาร ~28,000 บาท (4 คน)"},
    {"entity": "Bangkok Bank", "kind": "note", "date": "2026-04-10", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "ส่งของขวัญวันสงกรานต์ให้ คุณประยุทธ์: ชุด Afternoon Tea voucher โรงแรม Capella Bangkok 2 ใบ (สำหรับครอบครัว) มูลค่า ~6,000 บาท"},
    {"entity": "Bangkok Bank", "kind": "note", "date": "2026-06-05", "reporter": "exec", "sens": 2, "dept": "general",
     "text": "CEO พาคุณประยุทธ์ไปดูงาน AWS Summit Bangkok ด้วยกัน หลังจบงานไปทานข้าวที่ร้าน Paste (Gaysorn) คุยเรื่องแผน digital transformation 3 ปีของธนาคาร ได้ข้อมูลว่า budget IT ปีหน้าจะเพิ่ม 30% (fact, confidential). ค่าอาหาร ~12,000 บาท (2 คน)"},

    # PTT Digital
    {"entity": "PTT Digital", "kind": "note", "date": "2026-01-20", "reporter": "fin1", "sens": 1, "dept": "finance",
     "text": "ส่งกระเช้าปีใหม่ให้ผู้บริหาร PTT Digital 3 ท่าน: กระเช้า TWG Tea + ช็อกโกแลต Godiva มูลค่าชุดละ 5,500 บาท รวม 16,500 บาท"},
    {"entity": "PTT Digital", "kind": "meeting", "date": "2026-04-22", "reporter": "exec", "sens": 2, "dept": "general",
     "ours": "คุณสมชาย (CEO), Napat", "theirs": "คุณธนา (CEO PTT Digital), คุณพิชญา",
     "text": "เลี้ยงอาหารที่ร้าน Mezzaluna (lebua) ฉลองต่อสัญญา 3 ปี คุณธนาชอบ Italian fine dining เป็นพิเศษ (opinion). ระหว่างทานข้าว คุยเรื่อง strategic direction ของ PTT Group ที่จะเน้น AI/ML มากขึ้น (fact). ค่าอาหาร ~45,000 บาท (4 คน) งบพิเศษจาก CEO"},
    {"entity": "PTT Digital", "kind": "note", "date": "2026-06-12", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "ส่งของขวัญวันเกิดให้คุณพิชญา (Project Manager ฝั่ง PTT Digital): แจกันดอกไม้ + บัตรสตาร์บัคส์ 2,000 บาท รวมมูลค่า ~3,500 บาท คุณพิชญาโพสต์ขอบคุณใน LINE group"},

    # Additional: ข้อมูลสรุป preferences
    {"entity": "Microsoft Thailand", "kind": "note", "date": "2026-07-01", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "สรุป preferences ผู้ติดต่อ Microsoft Thailand: Khun Siriporn ชอบอาหาร Indian/German fine dining, ดื่มไวน์แดง. Mr. David Lim ชอบเล่นกอล์ฟ ชอบ whisky. Khun Thanaporn ชอบ dessert/cafe. งบเลี้ยงรับรองปกติ 10,000-25,000 บาท/ครั้ง"},
    {"entity": "Siam Cement Group", "kind": "note", "date": "2026-07-01", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "สรุป preferences ผู้ติดต่อ SCG: คุณวิชัย (CTO) ชอบอาหารญี่ปุ่น โดยเฉพาะ omakase, ดื่มสาเก. ชอบไวน์ฝรั่งเศส (Bordeaux). คุณสมหญิง ชอบกิจกรรมกลุ่ม/team building. งบเลี้ยงรับรองปกติ 8,000-20,000 บาท/ครั้ง"},
    {"entity": "Bangkok Bank", "kind": "note", "date": "2026-07-01", "reporter": "sales1", "sens": 1, "dept": "sales",
     "text": "สรุป preferences ผู้ติดต่อ Bangkok Bank: คุณประยุทธ์ (VP IT) ชอบ French cuisine เป็นพิเศษ ร้านประจำ Le Normandie. ชอบชา/afternoon tea กับครอบครัว. ไม่ดื่มแอลกอฮอล์. งบเลี้ยงรับรองปกติ 12,000-30,000 บาท/ครั้ง"},
]

for i, item in enumerate(SOCIAL_DATA, 1):
    ename = item["entity"]
    eid = entities.get(ename)
    if not eid:
        print(f"  SKIP: entity '{ename}' not found")
        continue

    reporter = item.get("reporter", "sales1")
    uid = users.get(reporter, users.get("sales1"))
    sens = item.get("sens", 1)
    dept = item.get("dept", "sales")

    if item["kind"] == "meeting":
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO interactions (entity_id,meeting_date,our_attendees,their_attendees,summary,created_by) VALUES (?,?,?,?,?,?)",
                (eid, item["date"], item.get("ours", ""), item.get("theirs", ""), item["text"], uid))
            iid = cur.lastrowid
        meta = f"Meeting {item['date']} | ours: {item.get('ours','')} | theirs: {item.get('theirs','')}"
        body = f"{meta}\n{item['text']}"
        ingest.ingest_chunks(ingest.chunk_text(body), entity_id=eid, interaction_id=iid,
                             sensitivity=sens, department=dept,
                             source_label=f"meeting:{item['date']}", created_by=uid)
    else:
        ingest.ingest_chunks([f"NOTE ({item['date']}): {item['text']}"],
                             entity_id=eid, sensitivity=sens, department=dept,
                             source_label=f"note:{item['date']}", created_by=uid)

    print(f"  [{i}/{len(SOCIAL_DATA)}] {item['kind']} - {item['entity']} - {item['date']}")

print("\nSocial/entertainment mock data complete!")
