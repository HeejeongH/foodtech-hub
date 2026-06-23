"""
Resend email client.
- Sends transactional + bulk emails
- Falls back to logging-only mode if RESEND_API_KEY missing (useful for local dev)
"""
import os, requests
from typing import Optional, List

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", "FoodTech Hub <onboarding@resend.dev>")
REPLY_TO = os.getenv("REPLY_TO", "").strip() or None
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")


def is_configured() -> bool:
    return bool(RESEND_API_KEY)


def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None,
    tags: Optional[List[dict]] = None,
) -> dict:
    """Returns {'id': ...} on success or {'error': ...} on failure."""
    if not RESEND_API_KEY:
        print(f"[email] DRY-RUN (no RESEND_API_KEY) → would send to {to}: {subject}")
        return {"id": "dry-run", "dry_run": True}
    try:
        payload = {
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text: payload["text"] = text
        if REPLY_TO: payload["reply_to"] = REPLY_TO
        if tags: payload["tags"] = tags
        r = requests.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# Templates
# ============================================================
def magic_link_email(login_url: str, email: str) -> tuple[str, str]:
    """Returns (subject, html) for the magic-link login email."""
    subject = "[FoodTech Hub] 관리자 로그인 링크"
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                   background:#f4f7fb;margin:0;padding:40px 20px;color:#1a1a1a">
  <table style="max-width:520px;margin:0 auto;background:white;border-radius:12px;
                box-shadow:0 4px 14px rgba(0,0,0,0.06);overflow:hidden" cellpadding="0" cellspacing="0">
    <tr><td style="background:#4d8bff;padding:24px 30px;color:white">
      <h1 style="margin:0;font-size:20px">FoodTech Hub</h1>
      <p style="margin:4px 0 0;opacity:0.8;font-size:13px">관리자 로그인</p>
    </td></tr>
    <tr><td style="padding:32px 30px">
      <p style="margin:0 0 16px">안녕하세요. <b>{email}</b> 계정의 관리자 로그인 요청을 받았습니다.</p>
      <p style="margin:0 0 24px;color:#555">아래 버튼을 누르시면 로그인됩니다. 이 링크는 <b>15분</b> 동안 유효합니다.</p>
      <p style="text-align:center;margin:24px 0">
        <a href="{login_url}" style="display:inline-block;background:#4d8bff;color:white;
            padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:600">관리자 페이지 열기</a>
      </p>
      <p style="margin:24px 0 0;color:#888;font-size:12px">
        본인이 요청하지 않은 경우 이 메일을 무시하세요.<br/>
        링크가 작동하지 않으면 이 주소를 복사해서 브라우저에 붙여넣으세요:<br/>
        <span style="color:#4d8bff;word-break:break-all">{login_url}</span>
      </p>
    </td></tr>
  </table>
</body></html>"""
    return subject, html


def newsletter_wrapper(subject: str, body_html: str, unsubscribe_url: str) -> str:
    """Wrap raw HTML body with header/footer + unsubscribe link."""
    return f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Apple SD Gothic Neo',sans-serif;
                   background:#f4f7fb;margin:0;padding:30px 16px;color:#1a1a1a;line-height:1.55">
  <table style="max-width:640px;margin:0 auto;background:white;border-radius:14px;
                box-shadow:0 4px 14px rgba(0,0,0,0.06);overflow:hidden" cellpadding="0" cellspacing="0" width="100%">
    <tr><td style="background:linear-gradient(135deg,#4d8bff,#7cc4ff);padding:22px 28px;color:white">
      <h1 style="margin:0;font-size:18px;letter-spacing:-0.01em">📬 FoodTech Hub Newsletter</h1>
      <p style="margin:4px 0 0;opacity:0.9;font-size:12px">{subject}</p>
    </td></tr>
    <tr><td style="padding:28px">
      {body_html}
    </td></tr>
    <tr><td style="background:#f4f7fb;padding:18px 28px;color:#888;font-size:11px;text-align:center;border-top:1px solid #e8edf4">
      서울대 푸드테크 최고책임자과정 / 월드푸드테크협의회<br/>
      이 뉴스레터를 더 받고 싶지 않으시면
      <a href="{unsubscribe_url}" style="color:#4d8bff">여기를 눌러 수신거부</a>하세요.
    </td></tr>
  </table>
</body></html>"""
