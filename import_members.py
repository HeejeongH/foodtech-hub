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
    """Map sheet columns to Member fields.

    Sheet structure (Google Sheets headers):
      대분류    : 사업 카테고리 (예: '서울대 푸드테크 최고책임자과정')
      소분류    : 기수 (예: '원우(10기)', '원우(9기)')  → cohort
      구분      : 대분류 카테고리 (기업/기관/대학/언론) → category
      세부구분  : 소분류 (일반/스타트업/대학/언론/기관/대기업/로펌/투자) → subcategory
      성명·직위·소속·소재지·세부소속·휴대폰·이메일
      * 총동문회: 회원여부 (정회원/임원/일반회원)         → membership_status
      * 월드푸드테크협의회: 혜택 % (100%/50%/20%)         → benefit_pct
      유료회원여부 (26.6.18.): 개인/기업/기관             → membership_type
      비고: 납입 이력 + 메모                              → notes + payment_history
      소속 (협의회 표기 기준): council_label
    """
    name = _norm(row.get("성명"))
    if not name: return None
    notes = _norm(row.get("비고"))
    # 비고에 "26.3 납입" 같은 텍스트가 들어가 있으면 payment_history로도 활용
    payment = None
    if notes and ("납입" in notes or "이후" in notes):
        payment = notes
    return {
        "name": name,
        "email": _split_email(row.get("이메일")),
        "phone": _norm_phone(row.get("휴대폰")),
        "cohort": _norm(row.get("소분류")),                                     # 원우(N기)
        "category": _norm(row.get("구분")),                                     # 기업/기관/대학/언론
        "subcategory": _norm(row.get("세부구분")),                              # 일반/스타트업/...
        "position": _norm(row.get("직위")),
        "organization": _norm(row.get("소속")),
        "location": _norm(row.get("소재지")),
        "division": _norm(row.get("세부소속")),
        "business_area": _norm(row.get("연구분야(대학소속) / 사업분야(기업소속)") or row.get("사업분야")),
        "membership_status": _norm(row.get("* 총동문회")) or _norm(row.get("회원 여부 (2025.04.01. 기준)")),
        "membership_type": _norm(row.get("유료회원여부 (26.6.18.)")),
        "payment_history": payment,
        "benefit_pct": _norm(row.get("* 월드푸드테크협의회")) or _norm(row.get("혜택 적용 여부 (수강료 감면)")),
        "council_label": _norm(row.get("소속 (협의회 표기 기준)")),
        "notes": notes,
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
