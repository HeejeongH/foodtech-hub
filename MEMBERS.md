# 회원 관리 & 뉴스레터 설정 가이드

푸드테크 최고책임자과정 원우 명단을 DB로 임포트하고 뉴스레터를 발송하기 위한 단계별 가이드.

---

## 1. Railway에서 Postgres 추가

1. Railway 프로젝트 → **`+ Create`** → **`Database`** → **`Add PostgreSQL`**
2. 자동으로 `DATABASE_URL`이 서비스 환경변수에 주입됩니다 (자동 연결)
3. 서비스 재배포 후 첫 부팅 시 테이블이 자동 생성됩니다

## 2. Resend API 설정

1. https://resend.com → 가입
2. **API Keys** → **Create API Key** → 키 복사
3. Railway Variables 탭에 추가:
   - `RESEND_API_KEY` = `re_xxxxx...`
   - `FROM_EMAIL` = `FoodTech Hub <onboarding@resend.dev>` (도메인 verify 전 기본값)
   - `REPLY_TO` = `your-email@example.com` (선택)

**자체 도메인 발신을 원하면**:
- Resend Dashboard → Domains → Add Domain → DNS 레코드(SPF/DKIM) 추가 → Verify
- 그 후 `FROM_EMAIL=FoodTech Hub <newsletter@yourdomain.kr>` 로 변경

## 3. 관리자 이메일 화이트리스트 추가

Railway Variables 탭:
```
ADMIN_EMAILS=heejeong@example.com,another@admin.com
```

여러 명이면 쉼표로 구분. 이 주소들로만 매직링크 로그인이 가능합니다.

## 4. PUBLIC_URL 설정 (매직링크에 들어갈 베이스 URL)

Railway Variables:
```
PUBLIC_URL=https://foodtech-hub-production-94de.up.railway.app
```

본인 도메인을 연결했다면 그걸로 입력.

## 5. 회원 명단 임포트

### 5-1. Google Sheet → CSV 내보내기

1. Google Sheets에서 명단 탭(예: "1. 최고책임자") 선택
2. **파일 → 다운로드 → 쉼표로 구분된 값(.csv)**
3. 파일명을 `members.csv`로 저장

### 5-2. 임포트 실행

**Railway 콘솔에서** (Web UI: 서비스 → Console 탭):
```bash
# CSV를 임시 위치에 업로드한 뒤
python import_members.py /tmp/members.csv
```

**또는 로컬에서 production DB에 직접 임포트**:
```bash
# Railway에서 DATABASE_URL 복사 (Variables 탭)
export DATABASE_URL='postgresql://user:pass@xxx.railway.internal:5432/railway'
python import_members.py members.csv
```

출력 예시:
```
[import] columns: ['연번', '대분류', '소분류', '구분', ...]
[import] done · created=98 updated=0 skipped=3
```

### 5-3. 결과 확인

브라우저에서 `https://your-url/admin` 접속 → 로그인 → 회원 관리 탭

---

## 6. 사용 흐름

### 관리자 로그인
1. `/admin` 접속
2. 등록된 이메일 입력 → "로그인 링크 받기"
3. 이메일에서 링크 클릭 → 자동 로그인 (30일 세션)

### 뉴스레터 발송
1. **뉴스레터 탭** → "최근 뉴스로 본문 생성" 버튼
2. 제목·인사말·본문 검토·수정
3. 발송 대상 필터 (기수별/정회원만 등)
4. "테스트 발송" → 본인 이메일로 미리보기 확인
5. "전체 발송" → 확인 다이얼로그 → 발송 시작

### 회원이 수신거부 시
- 모든 뉴스레터 하단의 "수신거부" 링크 클릭
- DB에 `subscribed=false`로 자동 표시
- 이후 모든 발송에서 자동 제외

---

## 7. 트러블슈팅

| 증상 | 해결 |
|---|---|
| 로그인 링크 메일이 안 옴 | (a) 스팸함 확인 (b) `ADMIN_EMAILS`에 본인 이메일이 있는지 확인 (c) `RESEND_API_KEY` 설정 확인 |
| 발송이 "DRY RUN"으로 콘솔에만 출력됨 | `RESEND_API_KEY` 미설정 — Railway Variables에 추가 |
| 임포트 후 회원이 안 보임 | (a) Railway 서비스 재시작 (b) CSV 헤더가 한글인지 확인 (c) `name` 컬럼이 비어있지 않은지 확인 |
| 매직링크가 만료됨 | 15분 후 자동 만료, 재요청 필요 |
| 다른 사람이 발송한 캠페인이 안 보임 | "최근 캠페인 보기" 버튼 클릭 |

## 8. 보안 노트

- **매직링크 토큰**: 15분 유효, 1회용
- **세션 쿠키**: 30일 유효, HttpOnly + SameSite=Lax
- **수신거부 토큰**: 회원별 고유 무한기간 (관리자가 회원 삭제·재생성 가능)
- **API**: 모든 `/api/admin/*`는 세션 쿠키 필수 (401 반환)
- **CSRF**: 매직링크는 GET이지만 1회용이라 안전. 발송 API는 POST + 쿠키 인증
