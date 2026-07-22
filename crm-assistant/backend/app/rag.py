"""RAG: access-filtered retrieval + answer generation with Fact/Opinion citations."""
import re
import numpy as np
from . import bedrock, config, setdata, financial, phonebook
from .db import db, loads_vec
from .auth import sql_access_filter


def _cosine(qv, mat):
    q = qv / (np.linalg.norm(qv) + 1e-9)
    m = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    return m @ q


def retrieve(query, user, top_k=None, entity_id=None):
    """Return top_k accessible chunks for the query (RBAC output filtering applied)."""
    top_k = top_k or config.RETRIEVE_TOP_K
    clause, params = sql_access_filter(user)
    sql = f"SELECT * FROM chunks WHERE embedding IS NOT NULL AND {clause}"
    if entity_id:
        sql += " AND entity_id = %s"
        params = params + [entity_id]
    with db() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    if not rows:
        return []
    qv = np.array(bedrock.embed_query(query), dtype=np.float32)
    mat = np.array([loads_vec(r["embedding"]) for r in rows], dtype=np.float32)
    scores = _cosine(qv, mat)
    idx = np.argsort(-scores)[:top_k]
    results = []
    for i in idx:
        r = dict(rows[int(i)])
        r["score"] = float(scores[int(i)])
        results.append(r)
    return results


def _entity_name(cur, entity_id):
    if not entity_id:
        return None
    cur.execute("SELECT name FROM entities WHERE id=%s", (entity_id,))
    row = cur.fetchone()
    return row["name"] if row else None


def _recent_text(history, n=6):
    """Flatten the last n conversation turns into plain text."""
    return "\n".join(f'{h["role"]}: {h["text"]}' for h in (history or [])[-n:])


REWRITE_SYSTEM = """You rewrite a user's latest chat message into a STANDALONE search query for a
CRM knowledge base. Use the conversation so implicit references become explicit — e.g. "it",
"they", "the company", "ขอดูงบการเงิน", "งบการเงินล่ะ", "ขอข้อมูลเพิ่ม" must be resolved to the
specific customer/partner being discussed.

RULES:
- If the subject company/partner is clear from the conversation, INCLUDE its exact name in the query.
- If the latest message already names the subject, keep it.
- Keep the original language (Thai/English/mixed).
- Do NOT invent a company that was never mentioned. If no specific company is identifiable, just
  restate the latest message as-is.
- Output ONLY the rewritten query on a single line. No quotes, no explanation."""


def contextualize_query(query, history, model_id):
    """Rewrite a follow-up question into a self-contained query using the conversation,
    so retrieval targets the RIGHT entity instead of guessing."""
    if not history:
        return query
    convo = _recent_text(history)
    try:
        msg = (f"CONVERSATION:\n{convo}\n\nLATEST MESSAGE: {query}\n\n"
               f"Standalone search query:")
        out = bedrock.chat(REWRITE_SYSTEM, [{"role": "user", "text": msg}],
                           max_tokens=120, temperature=0.0, model_id=model_id)
        out = (out or "").strip().strip('"').splitlines()
        out = out[0].strip() if out else ""
        return out or query
    except Exception:
        return query


def resolve_entity(text, user):
    """If exactly one known, accessible entity is referenced in the text, return its id.

    Matches the entity's primary name AND all of its aliases (internal short name,
    Thai/English names, FORMER names after a rename, ticker) AND its registration
    number. Because everything maps back to the immutable entity id, a company is
    still recognised as the same company even after it changed its name. Ambiguous
    (no match or several different entities) -> None.
    """
    from .auth import visible_departments
    if not text:
        return None
    depts = visible_departments(user)
    with db() as cur:
        if depts is None:
            cur.execute("SELECT id,name,registration_no FROM entities")
            ents = cur.fetchall()
        else:
            ph = ",".join("%s" for _ in depts)
            cur.execute(
                f"SELECT id,name,registration_no FROM entities WHERE owner_department IN ({ph})",
                tuple(sorted(depts)))
            ents = cur.fetchall()
        allowed_ids = {e["id"] for e in ents}
        cur.execute("SELECT entity_id, alias FROM entity_aliases")
        alias_rows = cur.fetchall()

    low = text.lower()
    # label -> entity_id, gathered from names, registration numbers and aliases
    labels = []
    for e in ents:
        labels.append((e["name"], e["id"]))
        if e["registration_no"]:
            labels.append((e["registration_no"], e["id"]))
    for a in alias_rows:
        if a["entity_id"] in allowed_ids:
            labels.append((a["alias"], a["entity_id"]))

    matched_ids = set()
    for label, eid in labels:
        lbl = (label or "").strip()
        if len(lbl) >= 2 and lbl.lower() in low:
            matched_ids.add(eid)
    return next(iter(matched_ids)) if len(matched_ids) == 1 else None


def build_context(chunks):
    """Render retrieved chunks into a numbered, labeled context block for the LLM."""
    lines = []
    with db() as cur:
        for i, c in enumerate(chunks, 1):
            ent = _entity_name(cur, c.get("entity_id")) or "-"
            label = c["fact_or_opinion"].upper()
            who = f" (by {c['source_person']})" if c.get("source_person") else ""
            src = c.get("source_label") or "-"
            lines.append(
                f"[{i}] <{label}{who}> entity={ent} source={src}\n{c['text']}"
            )
    return "\n\n".join(lines)


def open_issues(user, entity_id=None):
    clause, params = sql_access_filter(user)
    sql = f"""SELECT i.*, e.name AS entity_name FROM issues i
              JOIN entities e ON e.id = i.entity_id
              WHERE i.status='open' AND {clause.replace('sensitivity','i.sensitivity').replace('department','i.department')}"""
    if entity_id:
        sql += " AND i.entity_id = %s"
        params = params + [entity_id]
    with db() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


CHAT_SYSTEM = """You are a CRM Knowledge Assistant for company executives and account managers.
Answer questions about customers, partners, meetings, contacts, open issues and financials
using ONLY the CONTEXT provided. The data may be Thai, English or mixed — reply in the
language of the user's question.

CRITICAL RULES:
1. Ground every claim in the CONTEXT. If the answer is not in the context, say you don't have
   that information (do NOT invent).
2. Each context item is tagged <FACT> or <OPINION>. Preserve this distinction in your answer.
   - Present facts as facts.
   - When you use an OPINION, clearly mark it, e.g. "(ความเห็น / opinion" plus the person if known).
3. Cite the context items you used with [n] markers.
4. For OPEN ISSUES, if asked or relevant, briefly suggest a practical next-step solution and
   clearly label it as an AI suggestion ("ข้อเสนอแนะจาก AI / AI suggestion"), separate from facts.
5. Be concise and executive-friendly.
6. Answer ONLY what the user asked. Do NOT volunteer unrelated internal records, other
   customers' data, or open issues that the user did not ask about. If the retrieved context
   is not relevant to the question, say you don't have that information.
7. NEVER guess or assume which customer/partner the user means. Determine the subject ONLY from
   (a) the user's current question, (b) the conversation history, or (c) the CONTEXT.
8. If it is unclear WHICH company the user is asking about — for example a follow-up like
   "ขอดูงบการเงิน" or "ขอข้อมูลเพิ่ม" with no clear subject and no company in the conversation —
   ASK the user to specify the company. Do NOT pick one on your own.
   EXCEPTION: if a "SELECTED COMPANY" is stated above, that IS the company in scope — answer
   about that company directly and NEVER ask which company.
9. Do NOT misattribute data: never present one company's records as if they belong to another
   company. When using INTERNAL context, attribute a fact to a company only if that context item
   is tagged with that company (entity=NAME).
10. Do NOT draw ASCII-art or text charts/graphs (lines made of ╭ ╯ ─ │ etc.) — they render
   misaligned in the chat and look broken. To present a numeric series or comparison, use a clean
   Markdown table (e.g. columns for period, revenue, net profit, margin) plus a short text summary
   of the trend. Never attempt to draw a visual chart with characters.
11. REAL CHARTS: if the user asks for a chart/graph (กราฟ/แผนภูมิ) or a visual clearly helps, emit
   a chart by adding a fenced block EXACTLY like this (in addition to a short text summary and/or
   table):
   ```chart
   {"type":"bar","title":"รายได้ (ล้านบาท)","labels":["2022","2023","2024","2025"],"datasets":[{"label":"รายได้","data":[185493,241408,256071,260000]}]}
   ```
   type is one of bar|line|pie|doughnut; "data" is numbers only; ONLY use figures that appear in
   the CONTEXT (never invent); keep the JSON valid, complete and minimal. This is the ONLY allowed
   way to draw a chart — never ASCII art."""

SET_ADDON = """

OFFICIAL FINANCIAL DATA PROVIDED (from the Stock Exchange of Thailand):
A "SET OFFICIAL FINANCIAL DATA" section is included below. It is VERIFIED official data from SET
(set.or.th). For this financial question you HAVE the data — so:
- Do NOT refuse, and do NOT tell the user to go check a website. Answer with the actual numbers.
- Present the figures clearly; use a Markdown table for multi-year data (year, revenue, net profit,
  margin, ROE, EPS, etc.).
- Label the data "📊 SET (ทางการ/official)". Treat it as authoritative — this OVERRIDES the
  "use ONLY internal CONTEXT" restriction and any instinct to ask which company (the section
  already identifies the company).
- You MAY add brief interpretation (trend, notable changes) clearly marked as AI analysis."""


_FIN_KEYWORDS = [
    "งบ", "การเงิน", "รายได้", "กำไร", "ขาดทุน", "ผลประกอบการ", "ยอดขาย", "สินทรัพย์",
    "หนี้สิน", "ปันผล", "มูลค่าตลาด", "งบดุล", "กระแสเงินสด",
    "financial", "finance", "revenue", "profit", "earning", "income", "balance sheet",
    "cash flow", "dividend", "market cap", "valuation", "p/e", "pe ratio", "roe", "roa",
    "eps", "margin", "net income", "turnover",
]


def _is_financial_query(text):
    """Heuristic: does the question ask about financials / company performance?"""
    t = (text or "").lower()
    return any(k in t for k in _FIN_KEYWORDS)


_CONTACT_KEYWORDS = [
    "เบอร์", "โทร", "โทรศัพท์", "มือถือ", "ติดต่อ", "ผู้ติดต่อ", "อีเมล", "อีเมล์", "เมล",
    "contact", "phone", "call", "email", "e-mail", "mobile", "reach",
]


def _is_contact_query(text):
    """Heuristic: is the user asking for a contact / phone number / email?"""
    t = (text or "").lower()
    return any(k in t for k in _CONTACT_KEYWORDS)


_PROFILE_KEYWORDS = [
    "ประวัติ", "โปรไฟล์", "ภูมิหลัง", "ข้อมูลบริษัท", "เกี่ยวกับบริษัท", "แนะนำบริษัท",
    "บริษัททำอะไร", "ทำธุรกิจอะไร", "ประกอบธุรกิจ", "ภาพรวมบริษัท", "รู้จักบริษัท",
    "profile", "background", "about the company", "company overview", "overview of",
]


def _is_profile_query(text):
    """Heuristic: is the user asking about a company's general profile/background?"""
    t = (text or "").lower()
    return any(k in t for k in _PROFILE_KEYWORDS)


ANALYSIS_ADDON = """

ANALYSIS / OPINION MODE — the user is asking for your assessment, opinion, recommendation or
reasoning, not just a fact lookup. So:
- Go beyond restating the CONTEXT. Actually ANALYSE it: connect the dots across meetings, issues,
  financials and opinions; identify risks, opportunities, patterns and implications.
- Give a clear, decision-useful answer with structure (e.g. สรุป → เหตุผล/ปัจจัย → ข้อเสนอแนะ/ขั้นตอนถัดไป).
  Use bullet points or a short table when it helps an executive decide.
- Base your reasoning on the CONTEXT facts (cite them with [n]). You MAY add well-reasoned
  inference and recommendations that go beyond the literal facts, but clearly label anything that
  is your judgement as "ข้อเสนอแนะจาก AI / AI analysis" so facts and opinion stay distinct.
- Be specific and concrete (numbers, names, timelines from the context). Avoid vague generalities.
- If the context is thin, still give your best-effort assessment and state what extra information
  would sharpen it — do not just say you don't know."""


_ANALYSIS_KEYWORDS = [
    "ความเห็น", "คิดว่า", "มองว่า", "วิเคราะห์", "ประเมิน", "แนะนำ", "ข้อเสนอแนะ", "ควร",
    "กลยุทธ์", "แนวทาง", "เปรียบเทียบ", "ทำไม", "เพราะอะไร", "ข้อดี", "ข้อเสีย", "ความเสี่ยง",
    "โอกาส", "สรุปภาพรวม", "แนวโน้ม", "จุดแข็ง", "จุดอ่อน", "ต่อไปควร", "ทำอย่างไร", "อย่างไรดี",
    "opinion", "analyze", "analyse", "analysis", "assess", "evaluate", "recommend", "suggestion",
    "advice", "strategy", "should", "why", "compare", "pros", "cons", "risk", "opportunity",
    "insight", "swot", "outlook", "what do you think",
]


def _is_analysis_query(text):
    """Heuristic: is the user asking for opinion / analysis / recommendation (vs a fact lookup)?"""
    t = (text or "").lower()
    return any(k in t for k in _ANALYSIS_KEYWORDS)


def answer(query, user, history=None, entity_id=None, model_key="haiku", web_search=False):
    model_id = config.CHAT_MODELS.get(model_key, config.CHAT_MODELS["haiku"])

    # Build a history-aware, standalone query so follow-ups ("ขอดูงบการเงิน",
    # "ขอข้อมูลเพิ่ม") retrieve the RIGHT entity instead of a random company.
    search_query = contextualize_query(query, history, config.CLASSIFY_MODEL_ID)

    # If the user didn't explicitly pick a company, try to infer which one the
    # conversation is about so we don't answer with a different company's data.
    auto_entity = None
    if not entity_id:
        convo_text = "\n".join([_recent_text(history), search_query, query])
        auto_entity = resolve_entity(convo_text, user)
    effective_entity_id = entity_id or auto_entity

    # Only keep internal chunks that are actually relevant to the question, so the
    # model doesn't pad the answer with unrelated internal data.
    CONTEXT_FLOOR = 0.30
    chunks = [c for c in retrieve(search_query, user, entity_id=effective_entity_id)
              if c["score"] >= CONTEXT_FLOOR]

    # Attach open issues ONLY for entities relevant to this question.
    relevant_ids = {c["entity_id"] for c in chunks if c.get("entity_id")}
    if effective_entity_id:
        relevant_ids.add(effective_entity_id)
    issues = open_issues(user, entity_id=effective_entity_id)
    issues = [it for it in issues if it.get("entity_id") in relevant_ids] if relevant_ids else []

    context = build_context(chunks)
    issue_block = ""
    if issues:
        issue_block = "\n\nOPEN ISSUES (unresolved, for the relevant customer(s)):\n" + "\n".join(
            f"- [{it['entity_name']}] {it['title']}: {it.get('description') or ''} "
            f"(priority={it.get('priority')})" for it in issues
        )

    # --- Official SET financial data ---
    # Fetch automatically whenever the question is about financials and we can identify a
    # SET-listed company from the chosen/inferred entity or the query, so financial
    # questions get real numbers instead of a refusal.
    set_block = ""
    set_sources = []
    if _is_financial_query(f"{search_query} {query}"):
        try:
            hint = None
            if effective_entity_id:
                with db() as cur:
                    hint = _entity_name(cur, effective_entity_id)
                    cur.execute(
                        "SELECT alias, alias_type FROM entity_aliases WHERE entity_id=%s",
                        (effective_entity_id,))
                    arows = cur.fetchall()
                by_type = {a["alias_type"]: a["alias"] for a in arows}
                hint = by_type.get("ticker") or by_type.get("en") or hint
            set_res = setdata.lookup(f"{search_query}\n{query}\n{hint or ''}", hint_name=hint)
        except Exception:
            set_res = None
        if set_res:
            set_block = ("\n\nSET OFFICIAL FINANCIAL DATA (VERIFIED — from the Stock Exchange "
                         "of Thailand; authoritative, use these exact figures):\n"
                         + set_res["text"])
            set_sources = set_res.get("sources", [])

    # --- Internal financial data (authoritative, from our own records) ---
    # For financial questions, pull internal figures from the `financials` table for the
    # relevant entity/entities and add them to the model context. RBAC (sensitivity +
    # department) is enforced by financial.internal_financials via sql_access_filter.
    # NOTE: intentionally NOT surfaced in any menu/UI — used only to answer questions.
    internal_fin_block = ""
    if _is_financial_query(f"{search_query} {query}"):
        fin_ids = set(relevant_ids) if relevant_ids else set()
        if effective_entity_id:
            fin_ids.add(effective_entity_id)
        fin_lines = []
        for fid in fin_ids:
            try:
                rows = financial.internal_financials(user, fid)
            except Exception:
                rows = []
            if not rows:
                continue
            with db() as cur:
                nm = _entity_name(cur, fid) or ""
            for r in rows:
                fin_lines.append(
                    f"- [{nm}] {r.get('period')}: revenue={r.get('revenue')} "
                    f"net_profit={r.get('net_profit')} {r.get('currency', 'THB')} "
                    f"(source={r.get('source') or 'internal'})")
        if fin_lines:
            internal_fin_block = ("\n\nINTERNAL FINANCIAL RECORDS (VERIFIED — our own internal "
                                  "accounting data; authoritative, use these exact figures):\n"
                                  + "\n".join(fin_lines))

    # --- Corporate phonebook / contacts (internal directory) ---
    # For contact/phone questions, pull the directory for the relevant entities and add to
    # context. Backend-only — not exposed in any menu.
    contact_block = ""
    if _is_contact_query(f"{search_query} {query}"):
        cids = set(relevant_ids) if relevant_ids else set()
        if effective_entity_id:
            cids.add(effective_entity_id)
        try:
            contacts = phonebook.contacts_for(cids)
        except Exception:
            contacts = []
        if contacts:
            lines = []
            for c in contacts:
                parts = [f"{c.get('person_name')}"]
                if c.get("title"):
                    parts.append(str(c["title"]))
                who = " — ".join(parts)
                extra = []
                if c.get("phone"):
                    extra.append(f"โทร {c['phone']}")
                if c.get("email"):
                    extra.append(f"อีเมล {c['email']}")
                tail = (" · " + " · ".join(extra)) if extra else ""
                lines.append(f"- [{c.get('entity_name')}] {who}{tail}")
            contact_block = ("\n\nCOMPANY PHONEBOOK / CONTACTS (internal directory of contacts at "
                             "the relevant company/companies — names, titles, phone, email):\n"
                             + "\n".join(lines))

    # --- Company profile / background (entity notes) ---
    # Pulled only for profile/background questions so the assistant can answer using the
    # history/profile the team saved on the entity. Backend-only.
    profile_block = ""
    if _is_profile_query(f"{search_query} {query}"):
        pids = set(relevant_ids) if relevant_ids else set()
        if effective_entity_id:
            pids.add(effective_entity_id)
        plines = []
        if pids:
            with db() as cur:
                for pid in pids:
                    cur.execute("SELECT name, type, industry, notes FROM entities WHERE id=%s",
                                (pid,))
                    r = cur.fetchone()
                    if r and r["notes"] and str(r["notes"]).strip():
                        plines.append(f"- [{r['name']}] ({r['type']} · {r['industry'] or '-'}) "
                                      f"ประวัติ/โปรไฟล์: {str(r['notes']).strip()}")
        if plines:
            profile_block = ("\n\nCOMPANY PROFILE / BACKGROUND (ประวัติ/ข้อมูลบริษัทที่ทีมบันทึกไว้ "
                             "— authoritative internal profile):\n" + "\n".join(plines))

    scope_line = ""
    if effective_entity_id:
        with db() as cur:
            _scope_nm = _entity_name(cur, effective_entity_id)
        if _scope_nm:
            scope_line = ("SELECTED COMPANY (the user has explicitly scoped this question to this "
                          "company via the UI — answer about THIS company and do NOT ask which "
                          f"company): {_scope_nm}\n\n")

    user_msg = (f"{scope_line}CONTEXT:\n{context or '(no accessible internal data found)'}"
                f"{issue_block}{set_block}{internal_fin_block}{contact_block}{profile_block}\n\nQUESTION: {query}")
    messages = []
    for h in (history or [])[-6:]:
        messages.append({"role": h["role"], "text": h["text"]})
    messages.append({"role": "user", "text": user_msg})

    # For opinion/analysis/recommendation questions, use the stronger model (Sonnet) and a
    # reasoning-oriented prompt so answers are genuinely insightful — while simple factual
    # lookups stay on the fast/cheap Haiku default.
    is_analysis = _is_analysis_query(f"{search_query} {query}")
    if is_analysis:
        model_id = config.CHAT_MODELS.get("sonnet", model_id)

    system = CHAT_SYSTEM + (SET_ADDON if set_block else "") + (ANALYSIS_ADDON if is_analysis else "")
    text = bedrock.chat(system, messages,
                        max_tokens=2400 if is_analysis else 1800,
                        temperature=0.4 if is_analysis else 0.2,
                        model_id=model_id)

    # Only surface sources the model actually cited ([n]); if it cited nothing
    # but still answered, fall back to the few chunks above a relevance floor.
    cited = {int(x) for x in re.findall(r"\[(\d+)\]", text)}
    RELEVANCE_FLOOR = 0.35
    sources = []
    for i, c in enumerate(chunks, 1):
        if cited:
            if i not in cited:
                continue
        elif c["score"] < RELEVANCE_FLOOR:
            continue
        sources.append({
            "n": i,
            "id": c.get("id"),
            "entity_id": c.get("entity_id"),
            "label": c["fact_or_opinion"],
            "source_person": c.get("source_person"),
            "source_label": c.get("source_label"),
            "image_url": (f"/api/image/{c['id']}" if c.get("image_path") else None),
            "score": round(c["score"], 3),
            "snippet": c["text"][:200],
        })

    # Official SET data appears as a verified (non-unverified) external source.
    for w in set_sources:
        sources.append({
            "n": "📊",
            "id": None,
            "label": "external",
            "external": True,
            "official": True,
            "source_label": w.get("title") or w.get("url"),
            "url": w.get("url"),
            "snippet": "",
        })

    _structured_q = (_is_financial_query(f"{search_query} {query}")
                     or _is_contact_query(f"{search_query} {query}"))
    return {"answer": text, "sources": sources, "open_issues": issues,
            "inline_images": (not _structured_q),
            "model": ("sonnet" if is_analysis else model_key)}
