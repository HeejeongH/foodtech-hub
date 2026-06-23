# 배포 가이드

세 가지 권장 경로. 가장 쉬운 순서대로 정리.

---

## 옵션 1. Railway (추천 · 가장 빠름)

**비용**: 사용량 기반, 일반적으로 월 $5 안쪽 / 무료 크레딧 $5/월 (작은 서비스는 사실상 무료)

### 단계

1. **GitHub에 코드 푸시**
   ```bash
   cd foodtech-hub-deploy
   git init
   git add .
   git commit -m "initial: FoodTech Hub"
   git remote add origin https://github.com/<USERNAME>/foodtech-hub.git
   git push -u origin main
   ```

2. **Railway 가입 & 프로젝트 생성**
   - https://railway.app → "Login with GitHub"
   - "New Project" → "Deploy from GitHub repo" → 방금 푸시한 리포지토리 선택
   - Railway가 `Dockerfile`을 자동으로 감지하고 빌드 시작 (3~5분)

3. **환경 변수 추가** (Variables 탭)
   - `DART_API_KEY` = `f2e7f4e08267aceffcae7b6bc809844990aa3fb3` (지금 사용 중인 키)
   - `BRAVE_API_KEY` = (선택, https://api.search.brave.com/app/keys 에서 발급)

4. **퍼시스턴트 볼륨 추가** (캐시 보존)
   - Settings → Volumes → New Volume
   - Mount Path: `/app/data`, Size: 1GB

5. **도메인 발급**
   - Settings → Networking → "Generate Domain"
   - `https://foodtech-hub-production.up.railway.app` 같은 URL 생성됨

6. **(선택) 커스텀 도메인 연결**
   - Settings → Networking → Custom Domain → CNAME 레코드 안내대로 설정

---

## 옵션 2. Render

**비용**: Free 플랜 가능 (15분 무활동 시 sleep) / Starter $7/월 (sleep 없음)

### 단계

1. GitHub 푸시 (위와 동일)

2. https://render.com → "New" → "Blueprint"
   - 리포지토리 선택 → Render가 `render.yaml`을 읽고 자동 구성
   - 디스크(1GB), 헬스체크 경로 자동 설정됨

3. Environment Variables에 API 키 입력 후 "Apply"

4. 빌드 완료 후 `https://foodtech-hub.onrender.com` 같은 URL이 발급됨

**주의**: Free 플랜은 15분 무활동 시 sleep → 첫 요청에 30초 정도 콜드 스타트 발생.
운영용이라면 Starter 이상 권장.

---

## 옵션 3. 자체 서버 / VPS (DigitalOcean, AWS EC2, NAS 등)

### Docker Compose로 간단히

`docker-compose.yml`:
```yaml
version: "3.9"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DART_API_KEY=${DART_API_KEY}
      - BRAVE_API_KEY=${BRAVE_API_KEY}
      - DATA_DIR=/app/data
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

```bash
docker compose up -d
```

### Nginx 리버스 프록시 + HTTPS

```nginx
server {
    server_name foodtech.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo certbot --nginx -d foodtech.example.com
```

---

## 배포 후 체크리스트

```bash
# 1. 헬스체크
curl https://your-domain/api/health
# {"status":"ok","ts":"..."}

# 2. 설정 확인
curl https://your-domain/api/config
# {"dart_enabled":true,"brave_enabled":true,"version":"2.0.0",...}

# 3. yfinance 동작
curl https://your-domain/api/quote/BYND

# 4. DART 동작
curl https://your-domain/api/dart/뉴로메카

# 5. 뉴스 갱신 (배포 직후 1회)
curl -X POST https://your-domain/api/news/refresh
```

---

## 비용 비교

| 플랫폼 | 무료 | 유료 | 특징 |
|---|---|---|---|
| Railway | $5 크레딧/월 | 사용량 ($5~/월) | 가장 빠른 셋업, 좋은 DX |
| Render | Free 가능 (sleep) | $7/월 | 무료 플랜 / Blueprint 편함 |
| Fly.io | 가능 (제약 많음) | $5~ | 글로벌 엣지 |
| DigitalOcean | × | $4~ Droplet | 완전 통제 / 직접 관리 |

**처음 배포한다면 Railway 추천**. 5분 안에 라이브 URL을 받을 수 있습니다.

---

## 트러블슈팅

### 빌드 실패: `yfinance` 설치 오류
- Python 3.11 사용 확인 (Dockerfile에 명시됨)

### `/api/dart/...`가 404
- `DART_API_KEY` 환경 변수 누락. 플랫폼 대시보드에서 추가

### 뉴스가 비어있음
- `BRAVE_API_KEY` 미설정 → 자동으로 Google News RSS 사용 (다소 노이즈 있음)
- `POST /api/news/refresh` 호출해서 강제 갱신

### 컨테이너가 계속 재시작
- 로그 확인: Railway는 Deployments → View Logs
- 보통 환경변수 오타 또는 PORT 바인딩 문제
