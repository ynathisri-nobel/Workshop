"""Authentication (JWT) and RBAC helpers for input & output access control."""
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from . import config
from .db import db

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return pwd.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)


def create_token(user_row) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_row["id"]),
        "username": user_row["username"],
        "role": user_row["role"],
        "department": user_row["department"],
        "allowed_sensitivity": user_row["allowed_sensitivity"],
        "can_input": user_row["can_input"],
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def get_current_user(token: str = Depends(oauth2)) -> dict:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    with db() as cur:
        cur.execute("SELECT * FROM users WHERE id=%s", (payload["sub"],))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


def user_from_token(token: str) -> dict:
    """Decode a user from a raw token string (e.g. passed as a query param for <img> src)."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    with db() as cur:
        cur.execute("SELECT * FROM users WHERE id=%s", (payload["sub"],))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


def require_input(user: dict = Depends(get_current_user)) -> dict:
    """Guard for endpoints that WRITE/ingest data (input-side authorization)."""
    if not user.get("can_input") and user.get("role") not in ("admin", "executive", "manager"):
        raise HTTPException(status_code=403, detail="You are not authorized to input data")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------- Output-side (retrieval) access control ----------

def visible_departments(user: dict):
    """Return None if the user can see ALL customer groups (admin/executive or group
    'all'), otherwise the set of customer groups (departments) the user may access.
    A user's `department` may list several groups separated by commas, e.g.
    'sales,vip'. The shared 'general' group is always visible."""
    if user.get("role") in ("admin", "executive"):
        return None
    raw = (user.get("department") or "general").strip()
    groups = {d.strip() for d in raw.split(",") if d.strip()}
    if "all" in groups or not groups:
        return None
    groups.add("general")
    return groups


def sql_access_filter(user: dict, table_alias: str = ""):
    """Build a SQL WHERE fragment + params enforcing sensitivity + department.
    Returns (clause_str, params_list). clause does NOT include leading AND."""
    prefix = f"{table_alias}." if table_alias else ""
    clauses = [f"{prefix}sensitivity <= %s"]
    params = [user["allowed_sensitivity"]]
    depts = visible_departments(user)
    if depts is not None:
        placeholders = ",".join("%s" for _ in depts)
        clauses.append(f"{prefix}department IN ({placeholders})")
        params.extend(sorted(depts))
    return " AND ".join(clauses), params
