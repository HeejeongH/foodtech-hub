"""
Admin & newsletter routes.
Mounted under /admin and /api/admin in app.py.
"""
import os, secrets, json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlmodel import Session, select, or_, func

from db import Member, Newsletter, SendLog, get_session, utcnow
from auth import (
    is_admin_email, issue_magic_link, consume_magic_link,
    create_admin_session, get_current_admin, get_current_admin_optional,
    SESSION_COOKIE, SESSION_DAYS, ADMIN_EMAILS,
)
from email_client import send_email, magic_link_email, newsletter_wrapper, PUBLIC_URL, is_configured as email_configured

router = APIRouter()


# ============================================================
# AUTH: magic link
# ============================================================
@router.post("/api/admin/auth/request")
def auth_request(
    email: str = Form(...),
    session: Session = Depends(get_session),
):
    """Send a magic link to email if it's in the admin whitelist."""
    email = email.strip().lower()
    if not is_admin_email(email):
        # Don't reveal whether email is in whitelist; pretend to send anyway.
        return {"sent": True, "demo": True}
    token = issue_magic_link(session, email)
    base = PUBLIC_URL or os.getenv("PUBLIC_URL","").rstrip("/")
    login_url = f"{base}/admin/auth/verify?token={token}"
    subject, html = magic_link_email(login_url, email)
    result = send_email(email, subject, html)
    return {"sent": True, "provider": result}


@router.get("/admin/auth/verify")
def auth_verify(
    token: str,
    session: Session = Depends(get_session),
):
    email = consume_magic_link(session, token)
    if not email or not is_admin_email(email):
        return HTMLResponse("<h1>로그인 실패</h1><p>토큰이 만료되었거나 권한이 없습니다.</p>", status_code=400)
    sess_token = create_admin_session(session, email)
    resp = RedirectResponse("/admin", status_code=302)
    resp.set_cookie(
        SESSION_COOKIE, sess_token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True, samesite="lax",
        secure=PUBLIC_URL.startswith("https") if PUBLIC_URL else True,
    )
    return resp


@router.post("/api/admin/auth/logout")
def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/api/admin/me")
def auth_me(admin: Optional[str] = Depends(get_current_admin_optional)):
    return {
        "logged_in": bool(admin),
        "email": admin,
        "email_configured": email_configured(),
        "admin_whitelist_count": len(ADMIN_EMAILS),
    }


# ============================================================
# MEMBERS CRUD
# ============================================================
@router.get("/api/admin/members")
def list_members(
    q: Optional[str] = None,
    cohort: Optional[str] = None,
    status: Optional[str] = None,
    subscribed: Optional[bool] = None,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    stmt = select(Member)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            Member.name.ilike(like),
            Member.email.ilike(like),
            Member.organization.ilike(like),
            Member.position.ilike(like),
        ))
    if cohort:
        stmt = stmt.where(Member.cohort == cohort)
    if status:
        stmt = stmt.where(Member.membership_status == status)
    if subscribed is not None:
        stmt = stmt.where(Member.subscribed == subscribed)
    total = session.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = session.exec(stmt.order_by(Member.cohort.desc(), Member.name).offset(offset).limit(limit)).all()
    return {"total": total, "count": len(rows), "items": [r.model_dump() for r in rows]}


@router.get("/api/admin/members/stats")
def member_stats(
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    """Aggregate counts for dashboard."""
    total = session.exec(select(func.count()).select_from(Member)).one()
    subscribed = session.exec(select(func.count()).select_from(Member).where(Member.subscribed == True)).one()
    with_email = session.exec(select(func.count()).select_from(Member).where(Member.email.is_not(None))).one()
    paid = session.exec(select(func.count()).select_from(Member).where(Member.membership_status == "정회원")).one()

    by_cohort_rows = session.exec(
        select(Member.cohort, func.count(Member.id)).where(Member.cohort.is_not(None)).group_by(Member.cohort)
    ).all()
    by_cohort = sorted([{"cohort": c, "count": n} for c, n in by_cohort_rows], key=lambda x: x["cohort"] or "")

    by_cat_rows = session.exec(
        select(Member.category, func.count(Member.id)).where(Member.category.is_not(None)).group_by(Member.category)
    ).all()
    by_category = [{"category": c, "count": n} for c, n in by_cat_rows]

    return {
        "total": total,
        "with_email": with_email,
        "subscribed": subscribed,
        "paid_members": paid,
        "by_cohort": by_cohort,
        "by_category": by_category,
    }


@router.post("/api/admin/members")
def create_member(
    payload: dict,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    m = Member(**{k: v for k, v in payload.items() if k in Member.model_fields})
    if not m.unsubscribe_token:
        m.unsubscribe_token = secrets.token_urlsafe(24)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m.model_dump()


@router.put("/api/admin/members/{member_id}")
def update_member(
    member_id: int,
    payload: dict,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    m = session.get(Member, member_id)
    if not m: raise HTTPException(404, "member not found")
    for k, v in payload.items():
        if k in Member.model_fields and k not in ("id","created_at"):
            setattr(m, k, v)
    m.updated_at = utcnow()
    session.add(m); session.commit(); session.refresh(m)
    return m.model_dump()


@router.delete("/api/admin/members/{member_id}")
def delete_member(
    member_id: int,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    m = session.get(Member, member_id)
    if not m: raise HTTPException(404, "not found")
    session.delete(m); session.commit()
    return {"ok": True}


@router.post("/api/admin/members/import")
async def import_members_file(
    file: UploadFile = File(...),
    admin: str = Depends(get_current_admin),
):
    """Upload an Excel (.xlsx) or CSV file with members. Existing rows
    (matched by email or name+org) are updated; new rows are created."""
    from import_members import read_file, import_rows
    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "file too large (>10MB)")
    try:
        rows = read_file(content, filename=file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"파일을 읽을 수 없습니다: {e}")
    if not rows:
        raise HTTPException(400, "데이터 행이 없습니다. 헤더와 데이터가 모두 있는지 확인하세요.")
    result = import_rows(rows)
    result["filename"] = file.filename
    result["rows_loaded"] = len(rows)
    return result


# ============================================================
# NEWSLETTERS
# ============================================================
@router.get("/api/admin/newsletters")
def list_newsletters(
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    rows = session.exec(select(Newsletter).order_by(Newsletter.created_at.desc()).limit(50)).all()
    return {"items": [r.model_dump() for r in rows]}


@router.post("/api/admin/newsletters")
def create_newsletter(
    payload: dict,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    n = Newsletter(
        subject=payload.get("subject","(제목 없음)"),
        html_body=payload.get("html_body",""),
        text_body=payload.get("text_body"),
        created_by=admin,
        target_filter=json.dumps(payload.get("filter") or {}, ensure_ascii=False),
    )
    session.add(n); session.commit(); session.refresh(n)
    return n.model_dump()


@router.post("/api/admin/newsletters/{nid}/preview")
def newsletter_preview(
    nid: int,
    payload: dict,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    """Send preview to admin's own email."""
    n = session.get(Newsletter, nid)
    if not n: raise HTTPException(404)
    test_email = payload.get("test_email") or admin
    unsubscribe_url = f"{PUBLIC_URL}/unsubscribe?token=PREVIEW_TOKEN"
    html = newsletter_wrapper(n.subject, n.html_body, unsubscribe_url)
    result = send_email(test_email, f"[미리보기] {n.subject}", html)
    return {"sent_to": test_email, "result": result}


@router.post("/api/admin/newsletters/{nid}/send")
def newsletter_send(
    nid: int,
    payload: dict,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    """Send to all matching subscribers. Synchronous for simplicity.
    For >500 recipients, refactor to background task."""
    n = session.get(Newsletter, nid)
    if not n: raise HTTPException(404)
    if n.status == "sent":
        raise HTTPException(400, "already sent")

    # Build recipient list
    f = payload.get("filter") or {}
    stmt = select(Member).where(Member.subscribed == True, Member.email.is_not(None))
    if f.get("cohort"): stmt = stmt.where(Member.cohort == f["cohort"])
    if f.get("status"): stmt = stmt.where(Member.membership_status == f["status"])
    members = session.exec(stmt).all()

    n.status = "sending"
    n.total_recipients = len(members)
    session.add(n); session.commit()

    sent_count = 0; failed_count = 0
    for m in members:
        if not m.email: continue
        if not m.unsubscribe_token:
            m.unsubscribe_token = secrets.token_urlsafe(24)
            session.add(m)
        unsubscribe_url = f"{PUBLIC_URL}/unsubscribe?token={m.unsubscribe_token}"
        html = newsletter_wrapper(n.subject, n.html_body, unsubscribe_url)
        result = send_email(m.email, n.subject, html, tags=[{"name":"newsletter","value":str(n.id)}])
        log = SendLog(
            newsletter_id=n.id, member_id=m.id, email=m.email,
            status="sent" if "id" in result else "failed",
            provider_id=result.get("id"),
            error=result.get("error"),
        )
        session.add(log)
        if "id" in result and not result.get("error"): sent_count += 1
        else: failed_count += 1

    n.sent_count = sent_count
    n.failed_count = failed_count
    n.status = "sent" if failed_count == 0 else ("sent" if sent_count > 0 else "failed")
    n.sent_at = utcnow()
    session.add(n); session.commit()
    return {"sent": sent_count, "failed": failed_count, "total": len(members)}


@router.get("/api/admin/newsletters/{nid}/recipients/preview")
def recipients_preview(
    nid: int,
    cohort: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    """Preview who would receive this newsletter (before actually sending)."""
    stmt = select(Member).where(Member.subscribed == True, Member.email.is_not(None))
    if cohort: stmt = stmt.where(Member.cohort == cohort)
    if status: stmt = stmt.where(Member.membership_status == status)
    members = session.exec(stmt).all()
    return {
        "count": len(members),
        "sample": [{"name": m.name, "email": m.email, "cohort": m.cohort, "org": m.organization} for m in members[:10]]
    }


# ============================================================
# Build newsletter from latest news (helper)
# ============================================================
@router.post("/api/admin/newsletters/from-news")
def newsletter_from_news(
    payload: dict,
    session: Session = Depends(get_session),
    admin: str = Depends(get_current_admin),
):
    """Auto-generate a newsletter draft from currently cached news."""
    from pathlib import Path
    cache_file = Path(os.getenv("DATA_DIR", "./data")) / "news_cache.json"
    if not cache_file.exists():
        raise HTTPException(400, "news cache empty — run /api/news/refresh first")
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    items = cache.get("items", [])
    max_items = payload.get("max_items", 8)
    items = items[:max_items]

    subject = payload.get("subject") or f"FoodTech Hub 주간 뉴스 · {datetime.now().strftime('%Y-%m-%d')}"
    intro = payload.get("intro") or "이번 주 푸드테크 산업의 주요 뉴스를 모아 보내드립니다."

    parts = [f'<p style="font-size:15px;margin:0 0 20px">{intro}</p>']
    for it in items:
        kind_badge = "📰 뉴스" if it.get("kind") == "news" else "📊 리포트"
        parts.append(f"""
<div style="border-left:3px solid #4d8bff;padding:14px 18px;margin:0 0 16px;background:#f7faff;border-radius:0 8px 8px 0">
  <div style="font-size:11px;color:#4d8bff;font-weight:700;letter-spacing:0.04em;margin-bottom:6px">{kind_badge} · {it.get('category','')}</div>
  <a href="{it['url']}" style="font-size:15px;font-weight:600;color:#1a1a1a;text-decoration:none">{it['title']}</a>
  <div style="font-size:13px;color:#555;margin-top:6px">{(it.get('summary') or '')[:160]}</div>
  <div style="font-size:11px;color:#888;margin-top:8px">{it.get('source','')} · {it.get('date','')} · <a href="{it['url']}" style="color:#4d8bff">원문 →</a></div>
</div>""")
    html_body = "\n".join(parts)

    n = Newsletter(
        subject=subject, html_body=html_body,
        created_by=admin, target_filter=json.dumps(payload.get("filter") or {}),
    )
    session.add(n); session.commit(); session.refresh(n)
    return n.model_dump()


# ============================================================
# UNSUBSCRIBE
# ============================================================
@router.get("/unsubscribe")
def unsubscribe(token: str, session: Session = Depends(get_session)):
    m = session.exec(select(Member).where(Member.unsubscribe_token == token)).first()
    if not m:
        return HTMLResponse("<h2>잘못된 링크입니다.</h2>", status_code=400)
    m.subscribed = False
    m.updated_at = utcnow()
    session.add(m); session.commit()
    return HTMLResponse(f"""
<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>수신거부 완료</title>
<style>body{{font-family:-apple-system,sans-serif;background:#f4f7fb;display:grid;place-items:center;height:100vh;margin:0}}
.card{{background:white;padding:40px 50px;border-radius:14px;box-shadow:0 4px 14px rgba(0,0,0,0.08);text-align:center;max-width:420px}}
h1{{color:#4d8bff;margin:0 0 12px;font-size:22px}}p{{color:#555;margin:0;line-height:1.6}}</style></head>
<body><div class="card">
<h1>✓ 수신거부 완료</h1>
<p><b>{m.name}</b>님({m.email})께 더 이상 뉴스레터를 보내지 않습니다.<br/>
다시 받고 싶으시면 관리자에게 문의해 주세요.</p>
</div></body></html>""")
