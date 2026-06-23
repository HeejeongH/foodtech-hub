"""
Database layer — SQLModel on top of SQLAlchemy.
Works with Postgres (production) and SQLite (local dev).
"""
import os
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, create_engine, Session, select

# DATABASE_URL examples:
#   postgresql://user:pass@host:5432/dbname   (Railway/Render)
#   sqlite:///./data/foodtech.db              (local dev, default)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/foodtech.db")
# Railway gives "postgres://..." — SQLAlchemy 2.x requires "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

def utcnow():
    return datetime.now(timezone.utc)

# ============================================================
# Models
# ============================================================
class Member(SQLModel, table=True):
    """푸드테크 최고책임자과정 원우 명단."""
    __tablename__ = "members"
    id: Optional[int] = Field(default=None, primary_key=True)

    # 식별·연락
    name: str = Field(index=True)
    email: Optional[str] = Field(default=None, index=True)
    phone: Optional[str] = None

    # 소속
    cohort: Optional[str] = Field(default=None, index=True)      # 원우(10기), 원우(9기)...
    category: Optional[str] = None                                # 대분류: 기업/기관/대학/언론
    subcategory: Optional[str] = None                             # 소분류: 스타트업/일반/기관/대학...
    position: Optional[str] = None                                # 직위
    organization: Optional[str] = None                            # 소속
    location: Optional[str] = None                                # 소재지
    division: Optional[str] = None                                # 세부소속
    business_area: Optional[str] = None                           # 사업분야/연구분야

    # 회원 상태
    membership_status: Optional[str] = Field(default=None, index=True)   # 정회원/임원/X
    membership_type: Optional[str] = None                                 # 개인/기업/기관
    payment_history: Optional[str] = None                                 # "26.3 납입" 등
    benefit_pct: Optional[str] = None                                     # 100% / 50% / 20%
    council_label: Optional[str] = None                                   # 협의회 표기 기준 명칭

    # 뉴스레터
    subscribed: bool = Field(default=True, index=True)            # 수신 동의 여부
    unsubscribe_token: Optional[str] = Field(default=None, unique=True)

    # 메타
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Newsletter(SQLModel, table=True):
    """관리자가 작성한 뉴스레터 캠페인."""
    __tablename__ = "newsletters"
    id: Optional[int] = Field(default=None, primary_key=True)
    subject: str
    html_body: str
    text_body: Optional[str] = None
    created_by: Optional[str] = None         # admin email
    status: str = Field(default="draft", index=True)   # draft | sending | sent | failed
    target_filter: Optional[str] = None      # JSON describing audience filter
    total_recipients: int = 0
    sent_count: int = 0
    failed_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    sent_at: Optional[datetime] = None


class SendLog(SQLModel, table=True):
    """뉴스레터 1통의 발송 로그."""
    __tablename__ = "send_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    newsletter_id: int = Field(index=True, foreign_key="newsletters.id")
    member_id: Optional[int] = Field(default=None, foreign_key="members.id")
    email: str = Field(index=True)
    status: str = Field(default="queued")    # queued | sent | failed | bounced | opened
    provider_id: Optional[str] = None         # Resend message id
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class MagicLink(SQLModel, table=True):
    """관리자 매직 링크 일회용 토큰."""
    __tablename__ = "magic_links"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    token: str = Field(unique=True, index=True)
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class AdminSession(SQLModel, table=True):
    """관리자 로그인 세션."""
    __tablename__ = "admin_sessions"
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True)
    session_token: str = Field(unique=True, index=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=utcnow)


def init_db():
    """Create tables. Called once at startup."""
    # ensure sqlite directory exists
    if DATABASE_URL.startswith("sqlite:///"):
        path = DATABASE_URL.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency."""
    with Session(engine) as session:
        yield session
