"""FastAPI application: auth, ingestion, chat, entities, issues, financial, admin."""
import os
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, ingest, rag, financial
from .db import db, init_db
from .auth import (hash_password, verify_password, create_token, get_current_user,
                   require_input, require_admin)

app = FastAPI(title="CRM Knowledge Assistant", version="1.0.0")


@app.on_event("startup")
def _startup():
    init_db()


# ---------------- Schemas ----------------
class ChatMsg(BaseModel):
    role: str
    text: str


class SummarizeRequest(BaseModel):
    messages: List[ChatMsg]
    title: Optional[str] = None


class ChatRequest(BaseModel):
    query: str
    entity_id: Optional[int] = None
    history: Optional[List[ChatMsg]] = None
    model: Optional[str] = "haiku"          # 'haiku' | 'sonnet'
    web_search: Optional[bool] = False


class ChatTextIngest(BaseModel):
    text: str
    entity_id: Optional[int] = None
    sensitivity: int = 1
    department: Optional[str] = None
    source_label: Optional[str] = "chat-input"
    force_label: Optional[str] = None  # 'fact' | 'opinion' | None(auto)
    event_date: Optional[str] = None   # date the info pertains to (YYYY-MM-DD)


class AliasIn(BaseModel):
    alias: str
    # short | th | en | former | ticker | registration | other
    alias_type: str = "other"


class EntityIn(BaseModel):
    name: str
    type: str = "customer"
    industry: Optional[str] = None
    owner_department: str = "general"
    notes: Optional[str] = None
    registration_no: Optional[str] = None
    # convenience name fields — stored as aliases so all of them are searchable
    short_name: Optional[str] = None      # internal short name / ตัวย่อภายใน
    name_th: Optional[str] = None         # Thai name
    name_en: Optional[str] = None         # English name
    ticker: Optional[str] = None          # SET symbol, if listed
    aliases: Optional[List[AliasIn]] = None  # any extra labels


class EntityUpdate(BaseModel):
    name: Optional[str] = None            # renaming keeps the same id (identity)
    type: Optional[str] = None
    industry: Optional[str] = None
    owner_department: Optional[str] = None
    notes: Optional[str] = None
    registration_no: Optional[str] = None


class InteractionIn(BaseModel):
    entity_id: int
    meeting_date: Optional[str] = None
    our_attendees: Optional[str] = None
    their_attendees: Optional[str] = None
    summary: str
    sensitivity: int = 1
    department: Optional[str] = None


class IssueIn(BaseModel):
    entity_id: int
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    sensitivity: int = 1
    department: Optional[str] = None
    event_date: Optional[str] = None   # date the issue arose / was reported


class ResolveIn(BaseModel):
    resolution: Optional[str] = None   # note on HOW the issue was resolved


class UserIn(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "viewer"
    department: str = "general"
    allowed_sensitivity: int = 1
    can_input: bool = False


# ---------------- Auth ----------------
@app.post("/api/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with db() as cur:
        cur.execute("SELECT * FROM users WHERE username=%s", (form.username,))
        row = cur.fetchone()
    if not row or not verify_password(form.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(row)
    return {"access_token": token, "token_type": "bearer",
            "user": {"username": row["username"], "full_name": row["full_name"],
                     "role": row["role"], "department": row["department"],
                     "allowed_sensitivity": row["allowed_sensitivity"],
                     "can_input": bool(row["can_input"])}}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "full_name": user["full_name"],
            "role": user["role"], "department": user["department"],
            "allowed_sensitivity": user["allowed_sensitivity"],
            "can_input": bool(user["can_input"])}


# ---------------- Entities ----------------
def _aliases_for(cur, entity_id):
    cur.execute(
        "SELECT id, alias, alias_type FROM entity_aliases WHERE entity_id=%s ORDER BY alias_type, id",
        (entity_id,))
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def _add_alias(cur, entity_id, alias, alias_type):
    alias = (alias or "").strip()
    if not alias:
        return
    cur.execute(
        "SELECT 1 FROM entity_aliases WHERE entity_id=%s AND lower(alias)=lower(%s)",
        (entity_id, alias))
    dup = cur.fetchone()
    if not dup:
        cur.execute(
            "INSERT INTO entity_aliases (entity_id, alias, alias_type) VALUES (%s,%s,%s)",
            (entity_id, alias, alias_type))


@app.get("/api/entities")
def list_entities(user: dict = Depends(get_current_user)):
    from .auth import visible_departments
    depts = visible_departments(user)
    with db() as cur:
        if depts is None:
            cur.execute("SELECT * FROM entities ORDER BY name")
            rows = cur.fetchall()
        else:
            ph = ",".join("%s" for _ in depts)
            cur.execute(
                f"SELECT * FROM entities WHERE owner_department IN ({ph}) ORDER BY name",
                tuple(sorted(depts)))
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["aliases"] = _aliases_for(cur, r["id"])
            out.append(d)
    return out


@app.post("/api/entities")
def create_entity(body: EntityIn, user: dict = Depends(require_input)):
    with db() as cur:
        cur.execute(
            "INSERT INTO entities (name,type,industry,owner_department,notes,registration_no) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (body.name, body.type, body.industry, body.owner_department, body.notes,
             body.registration_no))
        eid = cur.fetchone()["id"]
        for val, atype in [(body.short_name, "short"), (body.name_th, "th"),
                           (body.name_en, "en"), (body.ticker, "ticker")]:
            _add_alias(cur, eid, val, atype)
        if body.registration_no:
            _add_alias(cur, eid, body.registration_no, "registration")
        for a in (body.aliases or []):
            _add_alias(cur, eid, a.alias, a.alias_type)
    return {"id": eid}


@app.put("/api/entities/{entity_id}")
def update_entity(entity_id: int, body: EntityUpdate, user: dict = Depends(require_input)):
    """Update entity fields. Renaming keeps the SAME id (stable identity) and archives
    the previous name as a 'former' alias so the company stays findable by its old name."""
    with db() as cur:
        cur.execute("SELECT * FROM entities WHERE id=%s", (entity_id,))
        ent = cur.fetchone()
        if not ent:
            raise HTTPException(404, "Entity not found")
        if body.name and body.name.strip() and body.name.strip() != ent["name"]:
            _add_alias(cur, entity_id, ent["name"], "former")
        fields = {
            "name": body.name if (body.name and body.name.strip()) else ent["name"],
            "type": body.type or ent["type"],
            "industry": body.industry if body.industry is not None else ent["industry"],
            "owner_department": body.owner_department or ent["owner_department"],
            "notes": body.notes if body.notes is not None else ent["notes"],
            "registration_no": (body.registration_no if body.registration_no is not None
                                else ent["registration_no"]),
        }
        cur.execute(
            "UPDATE entities SET name=%s,type=%s,industry=%s,owner_department=%s,notes=%s,registration_no=%s WHERE id=%s",
            (fields["name"], fields["type"], fields["industry"], fields["owner_department"],
             fields["notes"], fields["registration_no"], entity_id))
        if fields["registration_no"]:
            _add_alias(cur, entity_id, fields["registration_no"], "registration")
    return {"ok": True, "id": entity_id}


@app.post("/api/entities/{entity_id}/aliases")
def add_entity_alias(entity_id: int, body: AliasIn, user: dict = Depends(require_input)):
    with db() as cur:
        cur.execute("SELECT 1 FROM entities WHERE id=%s", (entity_id,))
        ent = cur.fetchone()
        if not ent:
            raise HTTPException(404, "Entity not found")
        _add_alias(cur, entity_id, body.alias, body.alias_type)
    return {"ok": True}


@app.delete("/api/entities/{entity_id}/aliases/{alias_id}")
def delete_entity_alias(entity_id: int, alias_id: int, user: dict = Depends(require_input)):
    with db() as cur:
        cur.execute("DELETE FROM entity_aliases WHERE id=%s AND entity_id=%s", (alias_id, entity_id))
    return {"ok": True}


@app.delete("/api/entities/{entity_id}")
def delete_entity(entity_id: int, user: dict = Depends(require_input)):
    """Delete a customer/partner ONLY if it has no activity records."""
    labels = {
        "interactions": "บันทึกประชุม",
        "issues": "issue",
        "chunks": "ข้อมูลในคลังความรู้",
        "documents": "ไฟล์",
        "contacts": "ผู้ติดต่อ",
        "financials": "ข้อมูลการเงิน",
    }
    with db() as cur:
        cur.execute("SELECT id FROM entities WHERE id=%s", (entity_id,))
        ent = cur.fetchone()
        if not ent:
            raise HTTPException(404, "Entity not found")
        counts = {}
        for tbl in labels:
            cur.execute(f"SELECT COUNT(*) AS c FROM {tbl} WHERE entity_id=%s", (entity_id,))
            counts[tbl] = cur.fetchone()["c"]
        if sum(counts.values()) > 0:
            detail = ", ".join(f"{labels[k]} {v}" for k, v in counts.items() if v)
            raise HTTPException(
                409, f"ลบไม่ได้: ยังมีข้อมูลอยู่ ({detail}) — กรุณาลบข้อมูลเหล่านี้ก่อน")
        cur.execute("DELETE FROM entity_aliases WHERE entity_id=%s", (entity_id,))
        cur.execute("DELETE FROM entities WHERE id=%s", (entity_id,))
    return {"ok": True}


@app.get("/api/entities/{entity_id}")
def entity_detail(entity_id: int, user: dict = Depends(get_current_user)):
    from .auth import sql_access_filter
    with db() as cur:
        cur.execute("SELECT * FROM entities WHERE id=%s", (entity_id,))
        ent = cur.fetchone()
        if not ent:
            raise HTTPException(404, "Entity not found")
        aliases = _aliases_for(cur, entity_id)
        cur.execute("SELECT * FROM contacts WHERE entity_id=%s", (entity_id,))
        contacts = cur.fetchall()
        cur.execute(
            "SELECT * FROM interactions WHERE entity_id=%s ORDER BY meeting_date DESC",
            (entity_id,))
        inter = cur.fetchall()
        iclause, iparams = sql_access_filter(user)
        cur.execute(
            f"SELECT * FROM issues WHERE entity_id=%s AND {iclause} ORDER BY status, priority",
            [entity_id] + iparams)
        issues = cur.fetchall()
    return {"entity": dict(ent),
            "aliases": aliases,
            "contacts": [dict(c) for c in contacts],
            "interactions": [dict(x) for x in inter],
            "issues": [dict(x) for x in issues]}


# ---------------- Auto-detect resolved issues from note text ----------------
def _detect_resolved_issues(note_text, entity_id, user):
    """Check if a newly saved note implies that any open issues for the entity have been resolved."""
    from . import bedrock
    from .auth import sql_access_filter

    clause, params = sql_access_filter(user)
    acc = clause.replace('sensitivity', 'i.sensitivity').replace('department', 'i.department')
    with db() as cur:
        cur.execute(
            f"""SELECT i.id, i.title, i.description, i.priority, e.name AS entity_name
                FROM issues i JOIN entities e ON e.id = i.entity_id
                WHERE i.status='open' AND i.entity_id=%s AND {acc}""",
            [entity_id] + params)
        issues = cur.fetchall()
    if not issues:
        return []

    issue_list = "\n".join(
        f"[ID={r['id']}] {r['title']}: {(r['description'] or '')[:100]}"
        for r in issues
    )

    prompt = f"""Given this new note about a customer/partner:
---
{note_text[:500]}
---

And these OPEN issues for the same company:
{issue_list}

Which issues (if any) does the note indicate have been RESOLVED or FIXED?
Reply with ONLY a JSON array of issue IDs that are resolved, e.g. [3, 7].
If none are resolved, reply with [].
Reply ONLY with the JSON array, nothing else."""

    try:
        result = bedrock.chat(
            "You are a concise JSON-only assistant.", 
            [{"role": "user", "text": prompt}],
            max_tokens=100, temperature=0.0,
            model_id=config.CLASSIFY_MODEL_ID)
        import json, re as _re
        match = _re.search(r'\[[\d\s,]*\]', result or "")
        if not match:
            return []
        resolved_ids = set(json.loads(match.group()))
        return [{"id": r["id"], "title": r["title"], "entity_name": r["entity_name"],
                 "priority": r["priority"]}
                for r in issues if r["id"] in resolved_ids]
    except Exception:
        return []


# ---------------- Ingestion (INPUT side, RBAC guarded) ----------------
def _group_for(cur, entity_id, user, override=None):
    """Customer group (department) that a piece of data should belong to."""
    if override and override.strip() and override.strip() != "all":
        return override.strip()
    if entity_id:
        cur.execute("SELECT owner_department FROM entities WHERE id=%s", (entity_id,))
        row = cur.fetchone()
        if row and row["owner_department"]:
            return row["owner_department"]
    dept = (user.get("department") or "general").split(",")[0].strip()
    return "general" if dept in ("all", "") else dept


@app.post("/api/ingest/text")
def ingest_text(body: ChatTextIngest, user: dict = Depends(require_input)):
    with db() as cur:
        dept = _group_for(cur, body.entity_id, user, body.department)
    text = body.text
    if body.event_date:
        text = f"(ข้อมูล ณ วันที่ {body.event_date})\n{text}"
    n = ingest.ingest_chunks(
        ingest.chunk_text(text),
        entity_id=body.entity_id, sensitivity=body.sensitivity, department=dept,
        source_label=body.source_label, created_by=user["id"],
        default_label=body.force_label)

    detected_issues = []
    if body.entity_id:
        try:
            detected_issues = _detect_resolved_issues(body.text, body.entity_id, user)
        except Exception:
            pass

    return {"stored_chunks": n, "detected_issues": detected_issues}


@app.post("/api/ingest/file")
async def ingest_file(file: UploadFile = File(...),
                      entity_id: Optional[int] = Form(None),
                      sensitivity: int = Form(1),
                      department: Optional[str] = Form(None),
                      force_label: Optional[str] = Form(None),
                      user: dict = Depends(require_input)):
    data = await file.read()
    text = ingest.parse_file(file.filename, data)
    if not text.strip():
        raise HTTPException(400, "Could not extract text from file")
    safe = file.filename.replace("/", "_")
    path = os.path.join(config.UPLOAD_DIR, f"{user['id']}_{safe}")
    with open(path, "wb") as f:
        f.write(data)
    with db() as cur:
        dept = _group_for(cur, entity_id, user, department)
        cur.execute(
            "INSERT INTO documents (entity_id,filename,filetype,sensitivity,department,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (entity_id, file.filename, os.path.splitext(file.filename)[1], sensitivity, dept, user["id"]))
        doc_id = cur.fetchone()["id"]
    n = ingest.ingest_chunks(
        ingest.chunk_text(text), entity_id=entity_id, document_id=doc_id,
        sensitivity=sensitivity, department=dept, source_label=file.filename,
        created_by=user["id"], default_label=force_label)
    return {"document_id": doc_id, "stored_chunks": n, "chars": len(text)}


@app.post("/api/ingest/image")
async def ingest_image(file: UploadFile = File(...),
                       entity_id: Optional[int] = Form(None),
                       interaction_id: Optional[int] = Form(None),
                       note: Optional[str] = Form(None),
                       sensitivity: int = Form(1),
                       department: Optional[str] = Form(None),
                       source_label: Optional[str] = Form("image"),
                       user: dict = Depends(require_input)):
    """Attach an image: Claude vision describes/OCRs it."""
    from . import bedrock
    data = await file.read()
    ext = os.path.splitext(file.filename)[1].lower().lstrip(".") or "png"
    if ext not in bedrock.IMAGE_FORMATS:
        raise HTTPException(400, "Unsupported image type (png/jpg/jpeg/gif/webp)")
    with db() as cur:
        dept = _group_for(cur, entity_id, user, department)
    import uuid
    safe = f"img_{uuid.uuid4().hex}.{ext}"
    path = os.path.join(config.UPLOAD_DIR, safe)
    with open(path, "wb") as f:
        f.write(data)
    try:
        desc = bedrock.describe_image(data, fmt=ext, note=note)
    except Exception:
        desc = note or "(image attached)"
    text = f"[รูปภาพ] {note + ' — ' if note else ''}{desc}"
    n = ingest.ingest_chunks(
        [text], entity_id=entity_id, interaction_id=interaction_id,
        sensitivity=sensitivity, department=dept,
        source_label=source_label or file.filename, created_by=user["id"],
        image_path=safe)
    return {"stored_chunks": n, "image": safe}


@app.get("/api/image/{chunk_id}")
def get_image(chunk_id: int, token: str):
    """Serve an image with access control."""
    from .auth import user_from_token
    user = user_from_token(token)
    with db() as cur:
        row = _get_accessible_chunk(cur, chunk_id, user)
    if not row or not row["image_path"]:
        raise HTTPException(404, "Image not found or no access")
    path = os.path.join(config.UPLOAD_DIR, row["image_path"])
    if not os.path.isfile(path):
        raise HTTPException(404, "File missing")
    return FileResponse(path)


@app.post("/api/interactions")
def create_interaction(body: InteractionIn, user: dict = Depends(require_input)):
    with db() as cur:
        dept = _group_for(cur, body.entity_id, user, body.department)
        cur.execute(
            """INSERT INTO interactions (entity_id,meeting_date,our_attendees,their_attendees,summary,created_by)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (body.entity_id, body.meeting_date, body.our_attendees, body.their_attendees,
             body.summary, user["id"]))
        iid = cur.fetchone()["id"]
    meta = f"Meeting {body.meeting_date or ''} | ours: {body.our_attendees or '-'} | theirs: {body.their_attendees or '-'}"
    ingest.ingest_chunks(
        ingest.chunk_text(f"{meta}\n{body.summary}"),
        entity_id=body.entity_id, interaction_id=iid, sensitivity=body.sensitivity,
        department=dept, source_label=f"meeting:{body.meeting_date or iid}",
        created_by=user["id"])
    return {"interaction_id": iid}


# ---------------- Issues ----------------
@app.post("/api/issues")
def create_issue(body: IssueIn, user: dict = Depends(require_input)):
    with db() as cur:
        dept = _group_for(cur, body.entity_id, user, body.department)
        cur.execute(
            """INSERT INTO issues (entity_id,title,description,priority,sensitivity,department,created_by,event_date)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (body.entity_id, body.title, body.description, body.priority,
             body.sensitivity, dept, user["id"], body.event_date))
        iid = cur.fetchone()["id"]
    datestr = f" (วันที่ {body.event_date})" if body.event_date else ""
    ingest.ingest_chunks(
        [f"OPEN ISSUE{datestr}: {body.title}. {body.description or ''} (priority {body.priority})"],
        entity_id=body.entity_id, sensitivity=body.sensitivity, department=dept,
        source_label=f"issue:{iid}", created_by=user["id"], default_label="fact")
    return {"issue_id": iid}


@app.get("/api/issues")
def list_issues(status: str = "open", user: dict = Depends(get_current_user)):
    from .auth import sql_access_filter
    clause, params = sql_access_filter(user)
    acc = clause.replace('sensitivity', 'i.sensitivity').replace('department', 'i.department')
    if status == "all":
        where, qparams = acc, params
        order = "i.status, i.priority"
    else:
        where, qparams = f"i.status=%s AND {acc}", [status] + params
        order = "i.resolved_at DESC" if status == "resolved" else "i.priority"
    with db() as cur:
        cur.execute(
            f"""SELECT i.*, e.name AS entity_name, u.full_name AS resolved_by_name
                FROM issues i JOIN entities e ON e.id=i.entity_id
                LEFT JOIN users u ON u.id=i.resolved_by
                WHERE {where} ORDER BY {order}""",
            qparams)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, body: ResolveIn = ResolveIn(), user: dict = Depends(require_input)):
    with db() as cur:
        cur.execute(
            "UPDATE issues SET status='resolved', resolved_at=NOW(), resolution=%s, resolved_by=%s WHERE id=%s",
            (body.resolution, user["id"], issue_id))
    return {"ok": True}


# ---------------- Financial ----------------
@app.get("/api/financial/{entity_id}")
def get_financial(entity_id: int, user: dict = Depends(get_current_user)):
    return financial.financial_overview(user, entity_id)


# ---------------- Chat (OUTPUT side, RBAC filtered inside retrieval) ----------------
@app.post("/api/chat")
def chat_endpoint(body: ChatRequest, user: dict = Depends(get_current_user)):
    history = [m.dict() for m in (body.history or [])]
    return rag.answer(body.query, user, history=history, entity_id=body.entity_id,
                      model_key=(body.model or "haiku"), web_search=bool(body.web_search))


# ---------------- Admin: user management ----------------
@app.get("/api/admin/users")
def list_users(user: dict = Depends(require_admin)):
    with db() as cur:
        cur.execute("SELECT id,username,full_name,role,department,allowed_sensitivity,can_input FROM users")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/users")
def create_user(body: UserIn, user: dict = Depends(require_admin)):
    with db() as cur:
        cur.execute("SELECT 1 FROM users WHERE username=%s", (body.username,))
        exists = cur.fetchone()
        if exists:
            raise HTTPException(400, "Username already exists")
        cur.execute(
            """INSERT INTO users (username,password_hash,full_name,role,department,allowed_sensitivity,can_input)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (body.username, hash_password(body.password), body.full_name, body.role,
             body.department, body.allowed_sensitivity, int(body.can_input)))
    return {"ok": True}
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------- Summarize chat for PDF export ----------------
SUMMARIZE_SYSTEM = """You are a business report writer. Given a chat conversation between a user
and a CRM assistant, create a CONCISE executive summary report in Thai (or match the conversation language).

RULES:
1. Structure the report with clear sections using Markdown:
   - ## สรุปภาพรวม (1-2 paragraphs)
   - ## ประเด็นสำคัญ (bullet points)
   - ## ข้อมูลเชิงตัวเลข (use Markdown TABLE if any numbers/financials were discussed)
   - ## Issues / ปัญหาที่ค้าง (if any)
   - ## ข้อเสนอแนะ / Next Steps (if any)
2. Be CONCISE — combine repeated questions into one insight. Remove redundancy.
3. If financial data was discussed, present it as a clean Markdown table.
4. Keep the total length under 800 words.
5. Do NOT include the raw Q&A. This is a SUMMARY report.
6. Use professional business Thai language."""


@app.post("/api/chat/summarize")
def summarize_chat(body: SummarizeRequest, user: dict = Depends(get_current_user)):
    """Summarize a chat conversation into a concise report for PDF export."""
    from . import bedrock

    messages_text = "\n".join(
        f"{'Q' if m.role == 'user' else 'A'}: {m.text}" for m in body.messages
    )

    prompt = f"CONVERSATION TITLE: {body.title or 'Untitled'}\n\nFULL CONVERSATION:\n{messages_text}\n\nPlease write the executive summary report:"

    summary = bedrock.chat(
        SUMMARIZE_SYSTEM,
        [{"role": "user", "text": prompt}],
        max_tokens=2000, temperature=0.2,
        model_id=config.CHAT_MODELS.get("haiku"))

    return {"summary": summary}


# ---------------- Data correction: manage / edit / delete / flag chunks ----------------
class ChunkEdit(BaseModel):
    text: Optional[str] = None
    fact_or_opinion: Optional[str] = None  # 'fact' | 'opinion' | 'mixed'
    sensitivity: Optional[int] = None


class FlagIn(BaseModel):
    reason: Optional[str] = None


def _get_accessible_chunk(cur, chunk_id, user):
    from .auth import sql_access_filter
    clause, params = sql_access_filter(user)
    cur.execute(f"SELECT * FROM chunks WHERE id=%s AND {clause}",
                [chunk_id] + params)
    return cur.fetchone()


@app.get("/api/chunks")
def list_chunks(entity_id: Optional[int] = None, q: Optional[str] = None,
                flagged: Optional[int] = None, limit: int = 100,
                user: dict = Depends(require_input)):
    """List knowledge chunks the user may access, for review/correction."""
    from .auth import sql_access_filter
    clause, params = sql_access_filter(user, "c")
    sql = (f"SELECT c.id,c.text,c.fact_or_opinion,c.fo_confidence,c.source_person,"
           f"c.source_label,c.sensitivity,c.department,c.flagged,c.flag_reason,"
           f"c.entity_id,e.name AS entity_name,"
           f"u.full_name AS reporter_name,u.username AS reporter_username "
           f"FROM chunks c LEFT JOIN entities e ON e.id=c.entity_id "
           f"LEFT JOIN users u ON u.id=c.created_by WHERE {clause}")
    if entity_id:
        sql += " AND c.entity_id=%s"; params = params + [entity_id]
    if q:
        sql += " AND c.text LIKE %s"; params = params + [f"%{q}%"]
    if flagged:
        sql += " AND c.flagged=1"
    sql += " ORDER BY c.flagged DESC, c.created_at DESC LIMIT %s"; params = params + [limit]
    with db() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


@app.put("/api/chunks/{chunk_id}")
def edit_chunk(chunk_id: int, body: ChunkEdit, user: dict = Depends(require_input)):
    """Correct a chunk: update text (re-embed), label or sensitivity."""
    with db() as cur:
        row = _get_accessible_chunk(cur, chunk_id, user)
        if not row:
            raise HTTPException(404, "Chunk not found or no access")
        new_text = body.text if body.text is not None else row["text"]
        new_label = body.fact_or_opinion or row["fact_or_opinion"]
        new_sens = body.sensitivity if body.sensitivity is not None else row["sensitivity"]
    from . import bedrock
    from .db import dumps_vec
    emb = dumps_vec(bedrock.embed([new_text], input_type="search_document")[0]) if body.text is not None else None
    with db() as cur:
        if emb is not None:
            cur.execute(
                "UPDATE chunks SET text=%s, fact_or_opinion=%s, sensitivity=%s, embedding=%s, flagged=0, flag_reason=NULL WHERE id=%s",
                (new_text, new_label, new_sens, emb, chunk_id))
        else:
            cur.execute(
                "UPDATE chunks SET fact_or_opinion=%s, sensitivity=%s, flagged=0, flag_reason=NULL WHERE id=%s",
                (new_label, new_sens, chunk_id))
    return {"ok": True, "reembedded": body.text is not None}
    return {"ok": True, "reembedded": body.text is not None}


@app.delete("/api/chunks/{chunk_id}")
def delete_chunk(chunk_id: int, user: dict = Depends(require_input)):
    with db() as cur:
        row = _get_accessible_chunk(cur, chunk_id, user)
        if not row:
            raise HTTPException(404, "Chunk not found or no access")
        cur.execute("DELETE FROM chunks WHERE id=%s", (chunk_id,))
    return {"ok": True}


@app.post("/api/chunks/{chunk_id}/flag")
def flag_chunk(chunk_id: int, body: FlagIn, user: dict = Depends(get_current_user)):
    """Any user who can see a chunk may report it as incorrect."""
    with db() as cur:
        row = _get_accessible_chunk(cur, chunk_id, user)
        if not row:
            raise HTTPException(404, "Chunk not found or no access")
        cur.execute("UPDATE chunks SET flagged=1, flag_reason=%s, flagged_by=%s WHERE id=%s",
                     (body.reason, user["id"], chunk_id))
    return {"ok": True}


@app.post("/api/chunks/{chunk_id}/unflag")
def unflag_chunk(chunk_id: int, user: dict = Depends(require_input)):
    with db() as cur:
        row = _get_accessible_chunk(cur, chunk_id, user)
        if not row:
            raise HTTPException(404, "Chunk not found or no access")
        cur.execute("UPDATE chunks SET flagged=0, flag_reason=NULL WHERE id=%s", (chunk_id,))
    return {"ok": True}


# ---------------- Frontend (static SPA) ----------------
FRONTEND = os.path.abspath(config.FRONTEND_DIR)
if os.path.isdir(FRONTEND):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND, "index.html"))
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
