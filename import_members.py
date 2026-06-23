"""
Import members from a CSV (exported from the Google Sheet).

Usage:
    # 1. Export sheet → File → Download → CSV
    # 2. Save as ./members.csv (UTF-8)
    # 3. Run:
    python import_members.py members.csv

The expected columns (Korean headers from the sheet):
    연번, 대분류, 소분류, 구분, 세부구분, 성명, 직위, 소속, 소재지, 세부소속,
    휴대폰, 이메일, 회원여부, ..., 협의회 표기, 사업분야/연구분야, 비고

We're forgiving: missing columns just become NULL.
"""
import sys, csv, secrets, re
from pathlib import Path
from typing import Optional

from db import init_db, engine, Member
from sqlmodel import Session, select


def _norm(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    s = str(s).strip()
    if s in ("", "-", "—", "X", "x"): return None
    return s


def _norm_phone(s: Optional[str]) -> Optional[str]:
    if not s: return None
    # remove zero-width / weird chars, keep digits + dash
    s = re.sub(r"[^\d\-+]", "", s)
    return s or None


def _split_email(s: Optional[str]) -> Optional[str]:
    """Some cells contain two emails separated by comma. Keep the first."""
    if not s: return None
    s = s.replace("\n", ",").replace(";", ",")
    parts = [p.strip() for p in s.split(",") if "@" in p]
    return parts[0] if parts else None


def parse_row(row: dict) -> Optional[dict]:
    name = _norm(row.get("성명"))
    if not name: return None
    return {
        "name": name,
        "email": _split_email(row.get("이메일")),
        "phone": _norm_phone(row.get("휴대폰")),
        "cohort": _norm(row.get("세부구분")),     # 원우(10기)...
        "category": _norm(row.get("구분")),       # 기업/기관/대학/언론
        "subcategory": _norm(row.get("세부구분") if False else row.get("소분류")) if row.get("소분류") else None,
        "position": _norm(row.get("직위")),
        "organization": _norm(row.get("소속")),
        "location": _norm(row.get("소재지")),
        "division": _norm(row.get("세부소속")),
        "business_area": _norm(row.get("연구분야(대학소속) / 사업분야(기업소속)") or row.get("사업분야")),
        "membership_status": _norm(row.get("* 총동문회")) or _norm(row.get("회원 여부 (2025.04.01. 기준)")),
        "membership_type": _norm(row.get("가입 유형")),
        "payment_history": _norm(row.get("유료회원여부 (26.6.18.)") or row.get("납입이력")),
        "benefit_pct": _norm(row.get("* 월드푸드테크협의회") or row.get("혜택 적용 여부 (수강료 감면)")),
        "council_label": _norm(row.get("소속 (협의회 표기 기준)")),
        "notes": _norm(row.get("비고")),
    }


def upsert(session: Session, data: dict) -> tuple[str, Member]:
    """Returns ('created'|'updated', Member)."""
    existing = None
    if data.get("email"):
        existing = session.exec(select(Member).where(Member.email == data["email"])).first()
    if not existing:
        existing = session.exec(
            select(Member).where(Member.name == data["name"], Member.organization == data.get("organization"))
        ).first()
    if existing:
        for k, v in data.items():
            if v is not None: setattr(existing, k, v)
        if not existing.unsubscribe_token:
            existing.unsubscribe_token = secrets.token_urlsafe(24)
        session.add(existing)
        return "updated", existing
    m = Member(**data, unsubscribe_token=secrets.token_urlsafe(24))
    session.add(m)
    return "created", m


def import_csv(path: str):
    init_db()
    p = Path(path)
    if not p.exists():
        print(f"[error] file not found: {path}"); sys.exit(1)
    created = updated = skipped = 0
    with Session(engine) as session, open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # header sanity check
        print(f"[import] columns: {reader.fieldnames}")
        for i, row in enumerate(reader, 2):
            data = parse_row(row)
            if not data:
                skipped += 1; continue
            action, _ = upsert(session, data)
            if action == "created": created += 1
            else: updated += 1
            if (created + updated) % 50 == 0:
                session.commit()
        session.commit()
    print(f"[import] done · created={created} updated={updated} skipped={skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_members.py <csv-file>")
        sys.exit(1)
    import_csv(sys.argv[1])
