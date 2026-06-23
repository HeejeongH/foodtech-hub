# FoodTech Hub

푸드테크 산업의 뉴스 브리핑과 글로벌·국내 주요 기업의 시가총액·매출액·재무 데이터를 한 화면에서 보여주는 대시보드.

## 기능

- **실시간 시세 (yfinance)** — 글로벌 상장사 시가총액·매출·4년치 추이
- **DART OpenAPI 연동** — 한국 상장사 연결 재무제표 자동 추출, 비상장사는 공시 PDF 링크 제공
- **자동 뉴스 큐레이션** — Brave Search API 또는 Google News RSS 폴백, 언론사 화이트리스트 필터링
- **Chart.js 시각화** — 매출 추이 라인차트 + YoY 성장률 바차트

## 빠른 시작 (로컬)

```bash
# 1. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 DART_API_KEY, BRAVE_API_KEY 입력 (모두 선택)

# 2. 의존성 설치 & 실행
pip install -r requirements.txt
python app.py
# → http://localhost:8000
```

Docker로:
```bash
docker build -t foodtech-hub .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data foodtech-hub
```

## 배포 가이드

자세한 단계는 [DEPLOY.md](./DEPLOY.md) 참조.

### Railway (가장 빠름, ~5분)
1. https://railway.app 가입 → New Project → Deploy from GitHub
2. 이 리포지토리 선택 → Railway가 `Dockerfile` 자동 감지
3. Variables 탭에서 `DART_API_KEY`, `BRAVE_API_KEY` 입력
4. Settings → Networking → Generate Domain → 끝

### Render (무료 플랜 가능)
1. https://render.com → New → Blueprint → 이 리포지토리 연결
2. `render.yaml`을 자동 인식하고 디스크/헬스체크 자동 구성
3. Environment Variables에 API 키 입력

## API 키 발급

| 키 | 용도 | 무료 한도 | 발급처 |
|---|---|---|---|
| `DART_API_KEY` | 한국 상장사 재무제표 | 일 10,000회 | https://opendart.fss.or.kr |
| `BRAVE_API_KEY` | 뉴스 크롤링 | 월 2,000회 | https://api.search.brave.com/app/keys |

키 없이도 동작합니다:
- DART 없음 → 한국 기업은 메타데이터만 표시
- Brave 없음 → Google News RSS로 폴백 (필터링은 다소 느슨함)

## API 엔드포인트

| Path | 설명 |
|---|---|
| `GET /` | 프론트엔드 |
| `GET /api/config` | 서버 설정 (DART/Brave 활성화 여부) |
| `GET /api/quote/{ticker}` | yfinance 시세 (예: `BYND`, `348340.KQ`) |
| `GET /api/dart/{name}` | DART 재무제표 (예: `뉴로메카`) |
| `GET /api/news` | 캐시된 뉴스 |
| `POST /api/news/refresh` | 뉴스 강제 갱신 |
| `GET /api/companies` | 등록된 기업 메타데이터 |
| `GET /api/health` | 헬스체크 |

## 구조

```
.
├── app.py              # FastAPI 백엔드
├── static/index.html   # 프론트엔드 (단일 HTML, Chart.js CDN)
├── data/               # 캐시 (영속 볼륨 권장)
│   ├── news_cache.json
│   └── dart_corp_code.json
├── requirements.txt
├── Dockerfile
├── railway.json        # Railway 배포 설정
├── render.yaml         # Render 배포 설정
└── .env.example
```

## 라이선스 / 데이터 출처

- yfinance: Yahoo Finance 공개 데이터 (Apache 2.0)
- DART OpenAPI: 금융감독원 공시 데이터 (CC BY)
- 뉴스: 언론사 원문 링크만 제공, 본문 크롤링 안 함
