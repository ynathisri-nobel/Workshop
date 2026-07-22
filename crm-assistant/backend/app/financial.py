"""Financial data connector: internal DB + external (web search) stub.

External data is ALWAYS flagged as external/unverified so the executive knows the
difference between internal records (authoritative) and web-sourced figures.
"""
from .db import db
from .auth import sql_access_filter


def internal_financials(user, entity_id):
    """Return internal financial rows the user is allowed to see."""
    clause, params = sql_access_filter(user)
    sql = f"SELECT * FROM financials WHERE source_type='internal' AND entity_id=%s AND {clause}"
    with db() as cur:
        cur.execute(sql, [entity_id] + params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def external_financials(entity_name):
    """STUB: external financial lookup via search engine.

    In production, wire this to a real search/financial API (e.g. a market-data
    provider or web search + scrape). For the MVP we return a clearly-labeled
    placeholder so the pipeline and UI can be demonstrated end-to-end.
    """
    return {
        "source_type": "external",
        "source": "web-search-stub",
        "verified": False,
        "note": (
            f"[EXTERNAL/UNVERIFIED] No live web-search provider is configured in this MVP. "
            f"Connect a market-data or search API to fetch public financials for "
            f"'{entity_name}'. Treat any external figure as unverified until confirmed."
        ),
        "items": [],
    }


def financial_overview(user, entity_id):
    with db() as cur:
        cur.execute("SELECT * FROM entities WHERE id=%s", (entity_id,))
        ent = cur.fetchone()
    if not ent:
        return {"error": "entity not found"}
    return {
        "entity": dict(ent),
        "internal": internal_financials(user, entity_id),
        "external": external_financials(ent["name"]),
    }
