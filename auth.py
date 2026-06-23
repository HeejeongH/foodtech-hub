"""
Admin authentication via email magic links.
- Whitelisted emails only (ADMIN_EMAILS env)
- Token lasts 15 minutes for login, 30 days for session
"""
import os, secrets
from datetime import timedelta, timezone
from typing import Optional
from fastapi import Cookie, HTTPException, Depends, Request
from sqlmodel import Session, select
from db import MagicLink, AdminSession, utcnow, get_session


def _ensure_aware(dt):
    """SQLite drops tzinfo; treat naive datetimes as UTC."""
    if dt is None: return None
    if dt.tzinfo is None: return dt.replace(tzinfo=timezone.utc)
    return dt

ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}
SESSION_COOKIE = "ft_admin"
SESSION_DAYS = 30
MAGIC_TTL_MIN = 15


def is_admin_email(email: str) -> bool:
    if not email: return False
    if not ADMIN_EMAILS:
        # If no whitelist configured, deny everything (safer than allow-all).
        return False
    return email.strip().lower() in ADMIN_EMAILS


def issue_magic_link(session: Session, email: str) -> str:
    token = secrets.token_urlsafe(32)
    ml = MagicLink(
        email=email.strip().lower(),
        token=token,
        expires_at=utcnow() + timedelta(minutes=MAGIC_TTL_MIN),
    )
    session.add(ml)
    session.commit()
    return token


def consume_magic_link(session: Session, token: str) -> Optional[str]:
    """Return email if valid, else None. Marks token as used."""
    ml = session.exec(select(MagicLink).where(MagicLink.token == token)).first()
    if not ml: return None
    if ml.used_at: return None
    if _ensure_aware(ml.expires_at) < utcnow(): return None
    ml.used_at = utcnow()
    session.add(ml)
    session.commit()
    return ml.email


def create_admin_session(session: Session, email: str) -> str:
    session_token = secrets.token_urlsafe(32)
    s = AdminSession(
        email=email.strip().lower(),
        session_token=session_token,
        expires_at=utcnow() + timedelta(days=SESSION_DAYS),
    )
    session.add(s)
    session.commit()
    return session_token


def get_current_admin(
    request: Request,
    session: Session = Depends(get_session),
) -> str:
    """FastAPI dependency. Returns admin email or raises 401."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not_logged_in")
    s = session.exec(select(AdminSession).where(AdminSession.session_token == token)).first()
    if not s or _ensure_aware(s.expires_at) < utcnow():
        raise HTTPException(status_code=401, detail="session_expired")
    if not is_admin_email(s.email):
        raise HTTPException(status_code=403, detail="not_admin")
    return s.email


def get_current_admin_optional(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[str]:
    """Same but returns None instead of raising."""
    try:
        return get_current_admin(request, session)
    except HTTPException:
        return None
