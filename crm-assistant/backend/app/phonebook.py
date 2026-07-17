"""Corporate phonebook connector.

Provides contact directory info (name, title, phone, email) for customers and
partners so the chat/RAG can answer "who do we contact at X / what's their
number". Backed by the internal `contacts` table for the MVP; in production this
could be pointed at a real corporate phonebook/CRM directory API.

NOTE: intentionally NOT exposed in any UI menu — used only to answer questions.
"""
from .db import db


def contacts_for(entity_ids):
    """Return contact rows for the given entity ids (list/set/iterable).

    Access is gated by the caller passing only entity ids the user may see
    (the RAG passes RBAC-filtered relevant entities).
    """
    ids = [i for i in set(entity_ids or []) if i]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    sql = (f"SELECT c.entity_id, e.name AS entity_name, c.person_name, c.title, "
           f"c.phone, c.email "
           f"FROM contacts c LEFT JOIN entities e ON e.id = c.entity_id "
           f"WHERE c.entity_id IN ({placeholders}) "
           f"ORDER BY c.entity_id, c.id")
    with db() as conn:
        rows = conn.execute(sql, ids).fetchall()
    return [dict(r) for r in rows]
