"""
FoodTech Hub API (deployable)
- /api/quote/{ticker}   : yfinance 실시간 시세
- /api/dart/{name}      : DART OpenAPI (DART_API_KEY)
- /api/news             : Brave Search API + RSS 폴백
- /api/companies        : 기업 메타데이터
- /                     : 정적 프론트엔드
"""
import os, json, time, threading, traceback, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import requests
from dotenv import load_dotenv

# yfinance is imported lazily inside fetch_yf_quote() to keep
# startup fast — yfinance fetches a Yahoo cookie on first import
# which can hang for >30s on some networks (e.g. Railway).

load_dotenv()
ROOT = Path(__file__).parent
DATA = Path(os.getenv("DATA_DIR", ROOT / "data"))
DATA.mkdir(exist_ok=True, parents=True)

DART_API_KEY = os.getenv("DART_API_KEY", "").strip()
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()
PORT = int(os.getenv("PORT", "8000"))

NEWS_CACHE_FILE = DATA / "news_cache.json"
DART_CORP_FILE = DATA / "dart_corp_code.json"
QUOTE_CACHE = {}
QUOTE_TTL = 300  # 5 minutes

app = FastAPI(title="FoodTech Hub API", version="2.0.0")

# Lightweight health endpoint — defined FIRST so it works even if other
# routes fail to import. Railway/Render hit this for liveness probes.
@app.get("/api/health")
def health_early():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

# ============================================================
# COMPANY METADATA
# ============================================================
COMPANIES = [
    {"id":"doordash","name":"DoorDash","korName":"도어대시","ticker":"DASH","region":"global",
     "sector":"음식 배달 플랫폼","country":"🇺🇸 미국","founded":2013,
     "description":"미국 최대 음식 배달 플랫폼. 2025년 첫 연간 흑자 달성, 40개국 확장.",
     "tags":["음식배달","마켓플레이스","로지스틱스","광고"],
     "keywords":["doordash","도어대시","dash"], "dart_name":None},
    {"id":"uber","name":"Uber Technologies","korName":"우버 (우버이츠 포함)","ticker":"UBER","region":"global",
     "sector":"모빌리티·배달","country":"🇺🇸 미국","founded":2009,
     "description":"라이드셰어 + 우버이츠 + 화물 통합 플랫폼.",
     "tags":["라이드셰어","음식배달","광고","화물"],
     "keywords":["uber","우버","uber eats","우버이츠"], "dart_name":None},
    {"id":"coupang","name":"Coupang Inc.","korName":"쿠팡 (쿠팡이츠 포함)","ticker":"CPNG","region":"kr",
     "sector":"이커머스·배달","country":"🇰🇷 한국","founded":2010,
     "description":"한국 최대 이커머스 + 쿠팡이츠 + 쿠팡플레이 운영사.",
     "tags":["로켓배송","쿠팡이츠","쿠팡플레이","쿠팡프레시"],
     "keywords":["coupang","쿠팡","쿠팡이츠","cpng"], "dart_name":None},
    {"id":"baemin","name":"우아한형제들","korName":"배달의민족 (배민)","ticker":"","region":"kr",
     "sector":"음식 배달 플랫폼","country":"🇰🇷 한국","founded":2010,
     "description":"독일 Delivery Hero 자회사. 2025년 매출 5조 원 돌파.",
     "tags":["배달의민족","배민커넥트","배민키친","B마트"],
     "keywords":["우아한형제들","배달의민족","배민","baemin","woowa"],
     "dart_name":"우아한형제들"},
    {"id":"kurly","name":"컬리","korName":"마켓컬리 운영사","ticker":"","region":"kr",
     "sector":"신선식품 이커머스","country":"🇰🇷 한국","founded":2015,
     "description":"샛별배송 프리미엄 신선식품. 2025년 첫 연간 영업이익 흑자.",
     "tags":["샛별배송","마켓컬리","뷰티컬리","큐레이션"],
     "keywords":["kurly","컬리","마켓컬리"], "dart_name":"컬리"},
    {"id":"beyond","name":"Beyond Meat","korName":"비욘드미트","ticker":"BYND","region":"global",
     "sector":"식물성 대체육","country":"🇺🇸 미국","founded":2009,
     "description":"식물성 대체육 대표 상장사.",
     "tags":["식물성고기","비건","B2C","B2B 외식"],
     "keywords":["beyond meat","비욘드미트","bynd"], "dart_name":None},
    {"id":"oatly","name":"Oatly Group AB","korName":"오틀리","ticker":"OTLY","region":"global",
     "sector":"식물성 대체유 (귀리)","country":"🇸🇪 스웨덴","founded":1994,
     "description":"글로벌 1위 귀리우유 브랜드.",
     "tags":["귀리우유","비건","바리스타","유제품 대체"],
     "keywords":["oatly","오틀리","otly","귀리우유"], "dart_name":None},
    {"id":"instacart","name":"Maplebear (Instacart)","korName":"인스타카트","ticker":"CART","region":"global",
     "sector":"식료품 배달","country":"🇺🇸 미국","founded":2012,
     "description":"북미 1위 식료품 배달 플랫폼.",
     "tags":["식료품배달","리테일미디어","광고","B2B SaaS"],
     "keywords":["instacart","인스타카트","maplebear","cart"], "dart_name":None},
    {"id":"bear","name":"베어로보틱스","korName":"Bear Robotics","ticker":"","region":"kr",
     "sector":"서빙·자율주행 로봇","country":"🇰🇷 한국/🇺🇸 미국","founded":2017,
     "description":"서빙로봇 '서비' 글로벌 5만 대 이상 보급.",
     "tags":["서빙로봇","자율주행","iF디자인상","LG전자"],
     "keywords":["bear robotics","베어로보틱스","서비"], "dart_name":"베어로보틱스코리아"},
    {"id":"intake","name":"인테이크","korName":"Intake","ticker":"","region":"kr",
     "sector":"대체식품·맞춤영양","country":"🇰🇷 한국","founded":2013,
     "description":"대체식품 푸드테크 기업. 2025년 135억 원 시리즈C 유치.",
     "tags":["식물성단백","맞춤영양","이너뷰티","다이어트"],
     "keywords":["intake","인테이크"], "dart_name":"인테이크"},
    {"id":"neuromeka","name":"뉴로메카","korName":"Neuromeka","ticker":"348340.KQ","region":"kr",
     "sector":"협동로봇·조리로봇","country":"🇰🇷 한국","founded":2013,
     "description":"협동로봇 'Indy' 기반 외식업 조리 자동화. KOSDAQ 상장.",
     "tags":["협동로봇","조리자동화","휴머노이드","Indy"],
     "keywords":["neuromeka","뉴로메카","indy","348340"], "dart_name":"뉴로메카"},
    {"id":"spacef","name":"스페이스에프","korName":"Space F","ticker":"","region":"kr",
     "sector":"세포배양육","country":"🇰🇷 한국","founded":2020,
     "description":"국내 대표 세포배양육 스타트업.",
     "tags":["배양육","셀컬처","지속가능","Seed→A"],
     "keywords":["space f","스페이스에프","spacef"], "dart_name":None},
]

# ============================================================
# yfinance
# ============================================================
def fmt_money(v, currency="USD"):
    if v is None: return "—"
    try: v = float(v)
    except: return "—"
    sign = "-" if v < 0 else ""; v = abs(v)
    if currency == "KRW":
        if v >= 1e12: return f"{sign}{v/1e12:.2f}조 원"
        if v >= 1e8:  return f"{sign}{v/1e8:.0f}억 원"
        if v >= 1e4:  return f"{sign}{v/1e4:.0f}만 원"
        return f"{sign}{v:,.0f} 원"
    if v >= 1e12: return f"{sign}${v/1e12:.2f}T"
    if v >= 1e9:  return f"{sign}${v/1e9:.2f}B"
    if v >= 1e6:  return f"{sign}${v/1e6:.2f}M"
    if v >= 1e3:  return f"{sign}${v/1e3:.2f}K"
    return f"{sign}${v:,.0f}"

def fetch_yf_quote(ticker):
    import yfinance as yf  # lazy import
    t = yf.Ticker(ticker)
    info = {}
    try: info = t.info or {}
    except: info = {}
    fast = {}
    try: fast = t.fast_info or {}
    except: pass

    history = []
    try:
        fin = t.financials
        if fin is not None and not fin.empty and "Total Revenue" in fin.index:
            row = fin.loc["Total Revenue"].dropna()
            years = sorted(row.index, reverse=True)[:4]
            tmp = []
            for y in years:
                tmp.append({"year": str(y.year if hasattr(y,'year') else y)[:4], "rev_raw": float(row[y])})
            tmp_sorted = sorted(tmp, key=lambda x: x["year"])
            for i, item in enumerate(tmp_sorted):
                if i == 0:
                    item["growth"] = None
                else:
                    prev_r = tmp_sorted[i-1]["rev_raw"]
                    item["growth"] = round((item["rev_raw"]-prev_r)/abs(prev_r)*100, 1) if prev_r else None
            for item in sorted(tmp_sorted, key=lambda x: x["year"], reverse=True):
                history.append({
                    "year": item["year"],
                    "rev": fmt_money(item["rev_raw"], info.get("financialCurrency","USD")),
                    "rev_raw": item["rev_raw"],
                    "growth": item["growth"],
                })
    except Exception as e:
        print(f"[yf] history error for {ticker}: {e}")

    market_cap = info.get("marketCap") or fast.get("market_cap")
    cur_price = info.get("currentPrice") or fast.get("last_price")
    currency = info.get("currency") or fast.get("currency") or "USD"
    rev_ttm = info.get("totalRevenue")
    return {
        "ticker": ticker,
        "shortName": info.get("shortName") or info.get("longName") or ticker,
        "longName": info.get("longName") or "",
        "exchange": info.get("exchange") or fast.get("exchange") or "",
        "currency": currency,
        "price": cur_price,
        "previousClose": info.get("previousClose") or fast.get("previous_close"),
        "dayChange": info.get("regularMarketChangePercent"),
        "marketCap": market_cap,
        "marketCapDisplay": fmt_money(market_cap, currency) if market_cap else "—",
        "revenue": rev_ttm,
        "revenueDisplay": fmt_money(rev_ttm, currency) if rev_ttm else "—",
        "employees": info.get("fullTimeEmployees"),
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "website": info.get("website") or "",
        "history": history,
        "source": "yfinance",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/quote/{ticker}")
def api_quote(ticker: str):
    ticker = ticker.upper().strip()
    now = time.time()
    if ticker in QUOTE_CACHE:
        ts, payload = QUOTE_CACHE[ticker]
        if now - ts < QUOTE_TTL: return payload
    try:
        data = fetch_yf_quote(ticker)
        QUOTE_CACHE[ticker] = (now, data)
        return data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(502, f"yfinance error: {e}")

# ============================================================
# DART OpenAPI
# ============================================================
def ensure_dart_corp_code():
    if DART_CORP_FILE.exists():
        try: return json.loads(DART_CORP_FILE.read_text(encoding="utf-8"))
        except: pass
    if not DART_API_KEY: return {}
    print("[dart] downloading corpCode.zip ...")
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}"
    r = requests.get(url, timeout=30); r.raise_for_status()
    import io, zipfile, xml.etree.ElementTree as ET
    z = zipfile.ZipFile(io.BytesIO(r.content))
    xml_bytes = z.read(z.namelist()[0])
    root = ET.fromstring(xml_bytes)
    mapping = {}
    for child in root.findall("list"):
        name = (child.findtext("corp_name") or "").strip()
        code = (child.findtext("corp_code") or "").strip()
        stock = (child.findtext("stock_code") or "").strip()
        if name and code:
            mapping[name] = {"corp_code": code, "stock_code": stock}
    DART_CORP_FILE.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    print(f"[dart] cached {len(mapping)} companies")
    return mapping

def _pick_account(rows, sj_filter, name_match):
    for row in rows:
        if sj_filter and sj_filter not in (row.get("sj_nm") or ""): continue
        nm = (row.get("account_nm") or "").strip()
        ok = name_match(nm) if callable(name_match) else (nm == name_match)
        if not ok: continue
        amt = (row.get("thstrm_amount") or "").replace(",","").strip()
        try: return float(amt) if amt and amt != "-" else None
        except: return None
    return None

def fetch_dart_financials(corp_code):
    if not DART_API_KEY: raise RuntimeError("DART_API_KEY not configured")
    out = {"years": [], "listed": True}
    current_year = datetime.now().year
    no_data = 0
    for y in range(current_year-1, current_year-5, -1):
        url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
        params = {"crtfc_key": DART_API_KEY, "corp_code": corp_code,
                  "bsns_year": str(y), "reprt_code": "11011", "fs_div": "CFS"}
        try:
            r = requests.get(url, params=params, timeout=15)
            j = r.json()
            if j.get("status") != "000":
                params["fs_div"] = "OFS"
                j = requests.get(url, params=params, timeout=15).json()
            if j.get("status") != "000":
                no_data += 1; continue
            rows = j.get("list", [])
            revenue = _pick_account(rows, "손익", lambda n: n in ("매출액","수익(매출액)","영업수익"))
            op_income = _pick_account(rows, "손익", lambda n: n in ("영업이익","영업이익(손실)"))
            net_income = _pick_account(rows, "손익", lambda n: n in ("당기순이익","당기순이익(손실)"))
            if revenue:
                out["years"].append({"year": str(y), "revenue": revenue,
                                     "op_income": op_income, "net_income": net_income})
            if len(out["years"]) >= 4: break
        except Exception as e:
            print(f"[dart] {y} error: {e}")
    if no_data >= 3 and not out["years"]: out["listed"] = False
    return out

def fetch_dart_disclosures(corp_code, n=8):
    try:
        r = requests.get("https://opendart.fss.or.kr/api/list.json", params={
            "crtfc_key": DART_API_KEY, "corp_code": corp_code,
            "bgn_de": (datetime.now().replace(year=datetime.now().year-2)).strftime("%Y%m%d"),
            "end_de": datetime.now().strftime("%Y%m%d"), "page_count": n}, timeout=15)
        j = r.json()
        if j.get("status") != "000": return []
        return [{"report_nm": x.get("report_nm",""), "rcept_dt": x.get("rcept_dt",""),
                 "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x.get('rcept_no','')}"}
                for x in j.get("list",[])[:n]]
    except: return []

@app.get("/api/dart/{name}")
def api_dart(name: str):
    if not DART_API_KEY:
        return JSONResponse({"error":"DART_API_KEY not configured","demo":True}, status_code=200)
    mapping = ensure_dart_corp_code()
    if not mapping: raise HTTPException(503, "DART corp_code unavailable")
    hit = mapping.get(name)
    if not hit:
        for k,v in mapping.items():
            if name in k or k in name: hit = v; name = k; break
    if not hit: raise HTTPException(404, f"DART corp not found: {name}")
    fin = fetch_dart_financials(hit["corp_code"])
    history = []
    sorted_years = sorted(fin["years"], key=lambda x: x["year"])
    for i, y in enumerate(sorted_years):
        growth = None
        if i > 0 and sorted_years[i-1]["revenue"]:
            prev = sorted_years[i-1]["revenue"]
            growth = round((y["revenue"]-prev)/abs(prev)*100, 1)
        history.append({"year": y["year"], "rev": fmt_money(y["revenue"],"KRW"),
                        "rev_raw": y["revenue"], "growth": growth,
                        "op_income_display": fmt_money(y["op_income"],"KRW") if y["op_income"] else "—"})
    history.sort(key=lambda x: x["year"], reverse=True)
    latest = history[0] if history else {}
    disclosures = fetch_dart_disclosures(hit["corp_code"]) if not history else []
    return {
        "name": name, "corp_code": hit["corp_code"],
        "stock_code": hit.get("stock_code") or "", "listed": bool(hit.get("stock_code")),
        "revenue": latest.get("rev_raw"),
        "revenueDisplay": latest.get("rev") or "비공개 (비상장 외감)",
        "currency": "KRW", "history": history, "disclosures": disclosures,
        "note": None if history else "비상장사로 OpenAPI 매출 자동 추출 불가. 우측 공시 목록에서 감사보고서 PDF를 확인하세요.",
        "source": "DART OpenAPI", "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

# ============================================================
# News (Brave Search API + RSS fallback)
# ============================================================
NEWS_QUERIES = [
    ("푸드테크 기사 2026", "전체"),
    ("배달의민족 쿠팡이츠 매출 기사", "배달·플랫폼"),
    ("배양육 대체단백 투자유치 2026", "대체단백·배양육"),
    ("서빙로봇 조리로봇 푸드테크 기사", "로봇·자동화"),
    ("foodtech startup funding 2026", "투자·M&A"),
    ("cultivated meat regulation 2026", "정책·규제"),
]

NEWS_DOMAINS = {
    "yna.co.kr","chosun.com","joongang.co.kr","donga.com","hani.co.kr","khan.co.kr",
    "hankyung.com","mk.co.kr","sedaily.com","etnews.com","mt.co.kr","edaily.co.kr",
    "fnnews.com","businesspost.co.kr","ddaily.co.kr","zdnet.co.kr","techm.kr",
    "newspim.com","newsis.com","news1.kr","biz.chosun.com","e.chosunbiz.com",
    "chosunbiz.com","hkn24.com","kyosu.net","mhns.co.kr","beyondpost.co.kr",
    "gbnews.kr","irobotnews.com","withbuyer.com","cooknchefnews.com","kfmn.co.kr",
    "diarypoint.com","newstheai.com","dongascience.com","aitimes.com",
    "bloter.net","platum.kr","venturesquare.net","thebell.co.kr","mtn.co.kr",
    "ftoday.co.kr","mediapen.com","sisajournal.com","ohmynews.com","pressian.com",
    "reuters.com","bloomberg.com","wsj.com","ft.com","nytimes.com","cnbc.com",
    "techcrunch.com","theverge.com","venturebeat.com","wired.com","forbes.com",
    "businessinsider.com","fortune.com","axios.com","cnn.com","bbc.com",
    "foodnavigator.com","foodnavigator-usa.com","foodnavigator-asia.com",
    "foodbusinessnews.net","foodbev.com","fooddive.com","greenqueen.com.hk",
    "vegconomist.com","agfundernews.com","theguardian.com","apnews.com",
}
REPORT_DOMAINS = {
    "gfi.org","mintel.com","statista.com","euromonitor.com","pwc.com",
    "mckinsey.com","deloitte.com","kpmg.com","ey.com","bain.com",
    "krei.re.kr","kati.net","ipet.re.kr","mafra.go.kr","kotra.or.kr",
    "thevc.kr","innoforest.co.kr","dart.fss.or.kr",
    "investors.beyondmeat.com","ir.coupang.com","investor.uber.com",
}
BLOCKED_DOMAINS = {
    "blog.naver.com","youtube.com","youtu.be","m.youtube.com","instagram.com",
    "facebook.com","twitter.com","x.com","tiktok.com","brunch.co.kr",
    "tistory.com","medium.com","reddit.com","linkedin.com","threads.net",
    "researchnester.com","straitsresearch.com","marketsandmarkets.com",
    "grandviewresearch.com","mordorintelligence.com","fortunebusinessinsights.com",
    "imarcgroup.com","alliedmarketresearch.com","globenewswire.com",
    "prnewswire.com","businesswire.com","s-space.snu.ac.kr",
}

def extract_host(url):
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.","").lower()
    except: return ""

def extract_source(url):
    h = extract_host(url); return h.split(".")[0] if h else ""

def classify_source(url):
    host = extract_host(url)
    if not host: return None
    for b in BLOCKED_DOMAINS:
        if host == b or host.endswith("."+b) or b in host: return None
    for d in REPORT_DOMAINS:
        if host == d or host.endswith("."+d): return "report"
    for d in NEWS_DOMAINS:
        if host == d or host.endswith("."+d): return "news"
    if host.endswith(".go.kr") or host.endswith(".re.kr"): return "report"
    return None

def parse_date(s):
    if not s: return None
    s = s.strip()
    m = re.match(r"(\d+)\s*(hour|day|week|month|year)s?\s*ago", s, re.I)
    if m:
        n = int(m.group(1)); unit = m.group(2).lower()
        days = {"hour":0,"day":1,"week":7,"month":30,"year":365}[unit]*n
        return datetime.now() - timedelta(days=days)
    for fmt in ["%b %d, %Y","%B %d, %Y","%Y-%m-%d","%Y.%m.%d","%Y/%m/%d","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M:%SZ"]:
        try: return datetime.strptime(s.replace("Z",""), fmt)
        except: pass
    return None

def call_brave_search(query):
    """Brave Search API: https://api.search.brave.com/  (2k req/mo free)"""
    if not BRAVE_API_KEY: return []
    try:
        r = requests.get("https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 10, "freshness": "py", "search_lang": "ko,en"},
            headers={"Accept":"application/json","X-Subscription-Token": BRAVE_API_KEY},
            timeout=15)
        if r.status_code != 200:
            print(f"[brave] {r.status_code}: {r.text[:200]}"); return []
        j = r.json()
        results = []
        for w in j.get("web",{}).get("results",[])[:10]:
            results.append({
                "title": w.get("title",""),
                "link": w.get("url",""),
                "snippet": w.get("description",""),
                "date": w.get("age","") or (w.get("page_age","")[:10] if w.get("page_age") else ""),
            })
        return results
    except Exception as e:
        print(f"[brave] error: {e}"); return []

def strip_html(s: str) -> str:
    """Remove HTML tags + decode entities. Used for RSS descriptions."""
    if not s: return ""
    import html as _html
    # remove tags
    s = re.sub(r"<[^>]+>", " ", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return _html.unescape(s)

def call_rss_fallback():
    """RSS 폴백: Google News RSS는 키 없이도 동작."""
    import xml.etree.ElementTree as ET
    queries = [
        ("푸드테크", "전체"),
        ("배달의민족 OR 쿠팡이츠", "배달·플랫폼"),
        ("배양육 OR 대체단백", "대체단백·배양육"),
        ("서빙로봇 조리로봇", "로봇·자동화"),
        ("foodtech funding", "투자·M&A"),
    ]
    items = []
    for q, cat in queries:
        try:
            from urllib.parse import quote
            url = f"https://news.google.com/rss/search?q={quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
            r = requests.get(url, timeout=15)
            if r.status_code != 200: continue
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                title = strip_html(it.findtext("title") or "")
                link = (it.findtext("link") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                desc = strip_html(it.findtext("description") or "")
                items.append({"title": title, "link": link, "snippet": desc[:220],
                              "date": pub[:16], "category": cat})
        except Exception as e:
            print(f"[rss] {q}: {e}")
    return items

def refresh_news_cache():
    print(f"[news] refreshing (brave={bool(BRAVE_API_KEY)}) ...")
    cutoff = datetime.now() - timedelta(days=180)
    items = []
    if BRAVE_API_KEY:
        for q, cat in NEWS_QUERIES:
            for r in call_brave_search(q):
                url = r.get("link",""); title = r.get("title","")
                if not url or not title: continue
                kind = classify_source(url)
                if not kind: continue
                dt = parse_date(r.get("date",""))
                if dt and dt < cutoff: continue
                items.append({
                    "category": cat, "kind": kind, "title": title,
                    "summary": r.get("snippet",""), "url": url,
                    "source": extract_source(url), "date": r.get("date","") or "",
                    "_dt": dt.isoformat() if dt else "",
                })
    else:
        # RSS fallback (less filtered but free)
        for r in call_rss_fallback():
            url = r["link"]; title = r["title"]
            if not url or not title: continue
            kind = classify_source(url) or "news"  # accept all from Google News
            items.append({
                "category": r["category"], "kind": kind, "title": title,
                "summary": r.get("snippet",""), "url": url,
                "source": extract_source(url) or "news.google", "date": r.get("date",""),
                "_dt": "",
            })
    # dedupe
    seen = set(); deduped = []
    for it in items:
        if it["url"] in seen: continue
        seen.add(it["url"]); deduped.append(it)
    deduped.sort(key=lambda x: x.get("_dt","") or "0000", reverse=True)
    cache = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(deduped),
        "source": "brave" if BRAVE_API_KEY else "rss",
        "items": deduped[:40],
    }
    NEWS_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[news] cached {len(cache['items'])} items")
    return cache

@app.get("/api/news")
def api_news():
    if NEWS_CACHE_FILE.exists():
        try: return json.loads(NEWS_CACHE_FILE.read_text(encoding="utf-8"))
        except: pass
    return refresh_news_cache()

@app.post("/api/news/refresh")
def api_news_refresh():
    return refresh_news_cache()

def news_cron():
    """Refresh hourly check; rebuild if older than 24h.
    Delay first run by 60s so healthcheck can pass first."""
    time.sleep(60)
    while True:
        try:
            if not NEWS_CACHE_FILE.exists():
                refresh_news_cache()
            else:
                cache = json.loads(NEWS_CACHE_FILE.read_text(encoding="utf-8"))
                updated = datetime.fromisoformat(cache.get("updated_at","").replace("Z",""))
                age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - updated.replace(tzinfo=None)).total_seconds()/3600
                if age_h > 24: refresh_news_cache()
        except Exception as e:
            print(f"[cron] {e}")
        time.sleep(3600)

# Disable background cron during startup health probe by checking env
if os.getenv("DISABLE_CRON", "").lower() not in ("1","true","yes"):
    threading.Thread(target=news_cron, daemon=True).start()

# ============================================================
# Companies + Config
# ============================================================
@app.get("/api/companies")
def api_companies():
    return {"count": len(COMPANIES), "companies": COMPANIES,
            "dart_enabled": bool(DART_API_KEY)}

@app.get("/api/config")
def api_config():
    return {"dart_enabled": bool(DART_API_KEY),
            "brave_enabled": bool(BRAVE_API_KEY),
            "version": "2.0.0",
            "server_time": datetime.now(timezone.utc).isoformat()}

# ============================================================
# Static frontend
# ============================================================
@app.get("/")
def index():
    p = ROOT / "static" / "index.html"
    if not p.exists():
        return JSONResponse({"error": "frontend missing", "expected": str(p)}, status_code=500)
    return FileResponse(p)

# Mount static only if directory exists (avoid startup crash)
_static_dir = ROOT / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
