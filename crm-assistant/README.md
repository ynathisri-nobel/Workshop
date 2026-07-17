# CRM Knowledge Assistant (MVP)

ผู้ช่วยข้อมูลลูกค้า & พาร์ทเนอร์สำหรับผู้บริหาร — Web app เข้าผ่าน browser
ถาม-ตอบเกี่ยวกับลูกค้า/พาร์ทเนอร์ ประวัติการพบ ประเด็นค้าง (issues) พร้อมแนะนำแนวทางแก้
โดยแยกแยะ **Fact / Opinion** และควบคุมสิทธิ์การเข้าถึง (RBAC) ทั้งฝั่ง Input และ Output

## Stack
- Backend: FastAPI (Python) + SQLite
- AI: Amazon Bedrock — Claude Haiku 4.5 (chat) + Cohere Embed Multilingual (ไทย/อังกฤษ)
- Frontend: Static SPA (HTML/CSS/JS) เสิร์ฟจาก FastAPI
- Auth: JWT + bcrypt

## Features
- 💬 **RAG Chat**: ถามเป็นไทย/อังกฤษ ตอบพร้อมอ้างอิงแหล่งข้อมูล + badge Fact/Opinion
- 📥 **Input หลายทาง**: พิมพ์ chat, อัปโหลด Word/Excel/PPT/PDF/txt/minutes, บันทึกการประชุม, เพิ่ม issue
- 🏷️ **Fact vs Opinion**: ผู้ป้อนเลือกเองได้ หรือให้ AI จำแนกอัตโนมัติ
- ⚠️ **Issue tracking + AI solution suggestion** สำหรับประเด็นที่ยังไม่ได้แก้
- 💰 **Financial**: ข้อมูลภายใน (DB) + ช่องต่อ external (web-search stub, ติดป้าย "unverified")
- 🔐 **RBAC**: role + department + ระดับความลับ (1–3) กรองทั้งตอนเขียนและตอนตอบ

## Run
```bash
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
AWS_REGION=us-east-1 ./run.sh        # seeds demo data + starts server
# เปิด http://localhost:8000
```
ต้องมี AWS credentials ที่เข้าถึง Bedrock ได้ (region us-east-1) และเปิด model access ของ
Claude Haiku 4.5 + Cohere Embed Multilingual.

## Demo accounts
| user | pass | role | dept | เห็นระดับ≤ | input |
|------|------|------|------|-----------|-------|
| exec | exec123 | executive | all | 3 | ✔ |
| sales1 | sales123 | manager | sales | 2 | ✔ |
| viewer | view123 | viewer | sales | 1 | ✖ |
| fin1 | fin123 | manager | finance | 3 | ✔ |
| admin | admin123 | admin | all | 3 | ✔ |

ตัวอย่าง RBAC: `viewer` (ระดับ 1, sales) จะ **ไม่เห็น** ข้อมูล PTT Digital (ระดับ 3, finance)
ขณะที่ `exec` เห็นทั้งหมด

## API หลัก
- `POST /api/auth/login` · `GET /api/auth/me`
- `POST /api/chat` — RAG (กรองสิทธิ์ใน retrieval)
- `POST /api/ingest/text` · `POST /api/ingest/file` · `POST /api/interactions` — input (RBAC guarded)
- `GET/POST /api/issues` · `POST /api/issues/{id}/resolve`
- `GET /api/entities` · `GET /api/entities/{id}` · `GET /api/financial/{id}`
- `GET/POST /api/admin/users` (admin เท่านั้น)

## Known limitations (MVP → ต่อยอดได้)
- Vector search ทำใน-process ด้วย numpy (เหมาะ ~พัน-หมื่น chunk); scale ขึ้นค่อยย้ายไป pgvector/OpenSearch
- Fact/Opinion จำแนกระดับ chunk; badge แหล่งข้อมูลอาจหยาบกว่าการแยกในคำตอบ (คำตอบแยกละเอียดกว่า)
- External financial เป็น stub — ต่อ API ค้นหา/ตลาดจริงภายหลัง
- JWT_SECRET ตั้งใน env ก่อนขึ้น production; ปัจจุบัน SQLite ไฟล์เดียว
