# 아키텍처 전환 설계 문서

> 작성일: 2026-03-06
> 대상: tax_exam3 — "OX가 답이다 (세무사편)"
> 목적: Render → Cloudflare Pages 이전 + 문의하기 게시판 신규 구축 전체 설계

---

## 1. 현재 vs 새 아키텍처 비교

### 현재 (As-Is)

```
[사용자 브라우저]
        ↓ HTTP 요청
[Render (Docker Container)]
  Python 3.12 http.server
  + REST API 서버 (server.py, 1337줄)
  + 정적 파일 서빙 (HTML/CSS/JS)
        ↓ sqlite3 직접 연결
[data/questions.db (SQLite, 43MB)]
  - 문제       (5지선다 기출문제)
  - OX         (OX 문제)
  - 오답노트   (레거시, 현재 localStorage로 대체)
  - 공지게시판
  - qa_posts / qa_answers (코드 존재, 서비스 중단)
```

**문의하기 현재 상태:**
- contact.html: 이메일 주소 표시만 (mailto 링크)
- qa.html: "서비스 중단" 메시지만 표시
- 사용자가 질문을 남길 방법 없음, 개발자가 답변할 방법 없음

---

### 새 (To-Be)

```
[사용자 브라우저]
        ↓ 정적 파일           ↓ API 호출 (/api/*)
[Cloudflare Pages]     [Cloudflare Workers/Functions]
  HTML / CSS / JS               ↓                  ↓
  (자동 배포, GitHub 연동)
                       [Cloudflare D1]      [Supabase PostgreSQL]
                        SQLite 호환 DB        PostgreSQL DB
                        - 문제 (기출)          - inquiries (문의글)
                        - OX 문제              - inquiry_replies (답변)
                        - 공지게시판
```

**문의하기 새 상태:**
- contact.html: 실제 게시판 (문의 작성 + 목록 + 개발자 답변)
- qa.html: 제거 또는 contact.html로 리디렉션
- 개발자가 `contact.html?admin=1`에서 키 입력 후 답변 작성

---

## 2. 사용 서비스 요약

| 서비스 | 역할 | 기존 대응 | 무료 한도 |
|--------|------|-----------|-----------|
| **Cloudflare Pages** | 정적 파일 호스팅 (HTML/CSS/JS) | Render 정적 서빙 | 무제한 요청 |
| **Cloudflare Workers (Functions)** | 서버리스 API | server.py (Python) | 100k req/day |
| **Cloudflare D1** | SQLite 호환 DB | data/questions.db | 읽기 25M/day, 5GB 저장 |
| **Supabase** | PostgreSQL (게시판 전용) | qa_posts/qa_answers (비활성) | 500MB DB, API 무제한 |

**기술 선택 이유:**
- **Cloudflare Pages + Workers**: 같은 도메인에서 정적 파일과 API를 함께 제공, `functions/` 폴더만 추가하면 자동 Workers 배포
- **Cloudflare D1**: 기존 SQLite가 그대로 마이그레이션됨 (스키마 변경 불필요)
- **Supabase**: 게시판은 관계형 DB + RLS(Row Level Security)가 적합, Dashboard에서 개발자가 직접 확인/수정 가능

---

## 3. 새 디렉토리 구조

```
tax_exam3/
├── webapp/                          # Cloudflare Pages 배포 루트
│   ├── index.html
│   ├── mock-exam.html / .js
│   ├── ox-mode.html / .js
│   ├── game.html / .js
│   ├── wrong-note.html / .js
│   ├── notice.html / .js
│   ├── contact.html / .js           # 문의 게시판으로 개편
│   ├── local-user-data.js
│   ├── skin.js
│   ├── styles.css / game.css
│   └── functions/                   # Cloudflare Workers (자동 인식)
│       └── api/
│           ├── health.js            # GET /api/health
│           ├── questions.js         # GET /api/questions → D1
│           ├── notices.js           # GET,POST /api/notices → D1
│           ├── contact.js           # GET /api/contact → 정적 응답
│           ├── ox/
│           │   └── questions.js     # GET /api/ox/questions → D1
│           └── inquiry/
│               ├── posts.js         # GET,POST /api/inquiry/posts → Supabase
│               └── replies.js       # POST /api/inquiry/replies → Supabase
├── data/
│   ├── questions.db                 # D1 마이그레이션 소스 (로컬 개발용 유지)
│   └── OX문제/ ...
├── scripts/ ...
├── wrangler.toml                    # CF Pages + D1 설정 (신규)
├── Dockerfile                       # 삭제 예정 (마이그레이션 완료 후)
└── render.yaml                      # 삭제 예정 (마이그레이션 완료 후)
```

---

## 4. wrangler.toml 설정

```toml
name = "tax-exam3"
pages_build_output_dir = "webapp"
compatibility_date = "2024-01-01"

[[d1_databases]]
binding = "DB"
database_name = "tax-exam3-db"
database_id = "<wrangler d1 create 후 발급된 ID>"

# 로컬 개발용 (wrangler pages dev)
[dev]
port = 8788
```

**환경변수 (Cloudflare Pages 대시보드에서 설정):**

| 변수명 | 용도 | 민감도 |
|--------|------|--------|
| `NOTICE_ADMIN_KEY` | 공지게시판 관리자 키 | Secret |
| `INQUIRY_ADMIN_KEY` | 문의게시판 관리자 키 | Secret |
| `SUPABASE_URL` | Supabase 프로젝트 URL | Plain |
| `SUPABASE_ANON_KEY` | 공개 API 키 (일반 요청) | Plain |
| `SUPABASE_SERVICE_ROLE_KEY` | 관리자 전용 키 (RLS 우회) | Secret |
| `CONTACT_EMAIL` | 연락처 이메일 주소 | Plain |

---

## 5. Cloudflare D1 마이그레이션 (questions.db → D1)

D1은 SQLite와 완전 호환이므로 기존 스키마·쿼리를 수정 없이 그대로 사용 가능.

### 5-1. 마이그레이션 절차

```bash
# Step 1. Wrangler CLI 설치 및 로그인
npm install -g wrangler
wrangler login

# Step 2. D1 데이터베이스 생성
wrangler d1 create tax-exam3-db
# 출력된 database_id를 wrangler.toml에 복사

# Step 3. 테이블별 SQL dump (43MB DB는 분할 필요)
sqlite3 data/questions.db ".output data/dump_munj.sql" ".dump 문제"
sqlite3 data/questions.db ".output data/dump_ox.sql"   ".dump OX"
sqlite3 data/questions.db ".output data/dump_notice.sql" ".dump 공지게시판"

# Step 4. 로컬 D1에서 테스트
wrangler d1 execute tax-exam3-db --local --file=data/dump_munj.sql
wrangler d1 execute tax-exam3-db --local --file=data/dump_ox.sql
wrangler d1 execute tax-exam3-db --local --file=data/dump_notice.sql

# Step 5. 원격 D1에 적용
wrangler d1 execute tax-exam3-db --remote --file=data/dump_munj.sql
wrangler d1 execute tax-exam3-db --remote --file=data/dump_ox.sql
wrangler d1 execute tax-exam3-db --remote --file=data/dump_notice.sql
```

**주의사항:**
- D1은 단일 SQL 파일 크기 제한이 있음 (현재 최대 10MB/요청)
- 43MB SQLite → SQL dump는 수백 MB가 될 수 있으므로 반드시 테이블별 분할
- `오답노트` 테이블은 D1에 마이그레이션 불필요 (클라이언트 localStorage로 대체됨)
- `qa_posts`, `qa_answers` 테이블은 마이그레이션 불필요 (Supabase로 신규 구축)

### 5-2. D1 Functions 쿼리 패턴

```javascript
// webapp/functions/api/questions.js
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const year    = url.searchParams.get("year");
  const subject = url.searchParams.get("subject");

  if (!year || !subject) {
    return Response.json({ error: "year and subject required" }, { status: 400 });
  }

  const { results } = await env.DB.prepare(
    `SELECT 문제번호, 문제지문, 보기_1, 보기_2, 보기_3, 보기_4, 보기_5,
            답, 답_배포, 해설, 렌더_마크업
     FROM 문제
     WHERE 출제연도 = ? AND 과목 = ?
     ORDER BY 문제번호`
  ).bind(Number(year), subject).all();

  return Response.json({ questions: results });
}
```

---

## 6. Supabase 게시판 스키마

### 6-1. 테이블 생성 SQL

```sql
-- 문의 게시글
CREATE TABLE inquiries (
  id          BIGSERIAL    PRIMARY KEY,
  nickname    TEXT         NOT NULL CHECK (char_length(nickname) BETWEEN 1 AND 20),
  title       TEXT         NOT NULL CHECK (char_length(title) BETWEEN 1 AND 100),
  body        TEXT         NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000),
  subject     TEXT,
  year        INTEGER,
  question_no INTEGER,
  source      TEXT         CHECK (source IN ('ox', 'mock') OR source IS NULL),
  is_closed   BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 답변 (사용자 및 개발자)
CREATE TABLE inquiry_replies (
  id          BIGSERIAL    PRIMARY KEY,
  inquiry_id  BIGINT       NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
  is_admin    BOOLEAN      NOT NULL DEFAULT FALSE,
  nickname    TEXT         NOT NULL CHECK (char_length(nickname) BETWEEN 1 AND 20),
  body        TEXT         NOT NULL CHECK (char_length(body) BETWEEN 1 AND 3000),
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_inquiries_created  ON inquiries        (created_at DESC);
CREATE INDEX idx_replies_inquiry_id ON inquiry_replies  (inquiry_id);
```

### 6-2. Row Level Security (RLS)

```sql
-- RLS 활성화
ALTER TABLE inquiries       ENABLE ROW LEVEL SECURITY;
ALTER TABLE inquiry_replies ENABLE ROW LEVEL SECURITY;

-- 일반 사용자: 문의 조회 + 작성
CREATE POLICY "public_select_inquiries"
  ON inquiries FOR SELECT USING (true);

CREATE POLICY "public_insert_inquiries"
  ON inquiries FOR INSERT WITH CHECK (true);

-- 일반 사용자: 답변 조회
CREATE POLICY "public_select_replies"
  ON inquiry_replies FOR SELECT USING (true);

-- 관리자(service_role 키): RLS 우회 → INSERT 가능 (별도 정책 불필요)
-- service_role 키는 Workers Secret에 저장, 관리자 API 요청 시에만 사용
```

### 6-3. updated_at 자동 갱신 트리거

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_inquiries_updated_at
  BEFORE UPDATE ON inquiries
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

---

## 7. Workers Functions API 전체 설계

### 7-1. 기존 Python → Workers 변환 매핑

| 기존 Python 엔드포인트 | 새 Workers Function 파일 | 대상 DB |
|----------------------|--------------------------|---------|
| GET /api/health | functions/api/health.js | — |
| GET /api/questions | functions/api/questions.js | D1 |
| GET /api/ox/questions | functions/api/ox/questions.js | D1 |
| GET /api/notices | functions/api/notices.js | D1 |
| POST /api/notices | functions/api/notices.js | D1 |
| GET /api/contact | functions/api/contact.js | — (정적) |
| GET /api/inquiry/posts | functions/api/inquiry/posts.js | Supabase |
| POST /api/inquiry/posts | functions/api/inquiry/posts.js | Supabase |
| POST /api/inquiry/replies | functions/api/inquiry/replies.js | Supabase |

### 7-2. 공통 CORS 처리

```javascript
// webapp/functions/api/_middleware.js
export async function onRequest({ request, next }) {
  const response = await next();
  const headers = new Headers(response.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Content-Type, X-Notice-Admin-Key, X-Inquiry-Admin-Key");
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }
  return new Response(response.body, { status: response.status, headers });
}
```

### 7-3. 문의 게시글 API (Supabase)

```javascript
// webapp/functions/api/inquiry/posts.js

const SUPABASE_HEADERS = (key) => ({
  "apikey": key,
  "Authorization": `Bearer ${key}`,
  "Content-Type": "application/json",
});

// GET: 문의 목록 조회 (최신순, 답변 포함)
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const limit = Math.min(Number(url.searchParams.get("limit")) || 40, 100);

  // 문의 목록
  const postsRes = await fetch(
    `${env.SUPABASE_URL}/rest/v1/inquiries?select=*&order=created_at.desc&limit=${limit}`,
    { headers: SUPABASE_HEADERS(env.SUPABASE_ANON_KEY) }
  );
  if (!postsRes.ok) return Response.json({ error: "fetch failed" }, { status: 500 });
  const posts = await postsRes.json();

  // 답변 일괄 조회
  const ids = posts.map((p) => p.id).join(",");
  let replies = [];
  if (ids) {
    const repRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/inquiry_replies?inquiry_id=in.(${ids})&order=created_at.asc`,
      { headers: SUPABASE_HEADERS(env.SUPABASE_ANON_KEY) }
    );
    if (repRes.ok) replies = await repRes.json();
  }

  // 게시글에 답변 병합
  const replyMap = {};
  for (const r of replies) {
    (replyMap[r.inquiry_id] ??= []).push(r);
  }
  const items = posts.map((p) => ({ ...p, replies: replyMap[p.id] ?? [] }));

  return Response.json({ count: items.length, items });
}

// POST: 문의 작성
export async function onRequestPost({ request, env }) {
  const body = await request.json().catch(() => null);
  if (!body) return Response.json({ error: "invalid json" }, { status: 400 });

  const { nickname, title, body: text, subject, year, question_no, source } = body;
  if (!nickname?.trim() || !title?.trim() || !text?.trim()) {
    return Response.json({ error: "닉네임, 제목, 내용은 필수입니다." }, { status: 400 });
  }

  const res = await fetch(`${env.SUPABASE_URL}/rest/v1/inquiries`, {
    method: "POST",
    headers: { ...SUPABASE_HEADERS(env.SUPABASE_ANON_KEY), "Prefer": "return=representation" },
    body: JSON.stringify({ nickname, title, body: text, subject, year, question_no, source }),
  });
  if (!res.ok) return Response.json({ error: "등록 실패" }, { status: 400 });
  const [item] = await res.json();
  return Response.json({ ok: true, item });
}
```

### 7-4. 답변 API (관리자 인증)

```javascript
// webapp/functions/api/inquiry/replies.js
export async function onRequestPost({ request, env }) {
  const adminKey = request.headers.get("X-Inquiry-Admin-Key")?.trim();
  const isAdmin  = Boolean(adminKey && adminKey === env.INQUIRY_ADMIN_KEY);

  const body = await request.json().catch(() => null);
  if (!body) return Response.json({ error: "invalid json" }, { status: 400 });

  const { inquiry_id, nickname, body: text } = body;
  if (!inquiry_id || !nickname?.trim() || !text?.trim()) {
    return Response.json({ error: "inquiry_id, 닉네임, 내용은 필수입니다." }, { status: 400 });
  }

  // 관리자일 때는 service_role 키 사용 (RLS 우회 → is_admin=true 허용)
  const supabaseKey = isAdmin ? env.SUPABASE_SERVICE_ROLE_KEY : env.SUPABASE_ANON_KEY;

  const res = await fetch(`${env.SUPABASE_URL}/rest/v1/inquiry_replies`, {
    method: "POST",
    headers: {
      "apikey": supabaseKey,
      "Authorization": `Bearer ${supabaseKey}`,
      "Content-Type": "application/json",
      "Prefer": "return=representation",
    },
    body: JSON.stringify({
      inquiry_id: Number(inquiry_id),
      is_admin: isAdmin,
      nickname: isAdmin ? `${nickname} (관리자)` : nickname,
      body: text,
    }),
  });
  if (!res.ok) return Response.json({ error: "답변 등록 실패" }, { status: 400 });
  const [item] = await res.json();
  return Response.json({ ok: true, item });
}
```

---

## 8. 문의하기 게시판 UI 설계

### 8-1. contact.html 구조 개편

**기존:** 이메일 주소 표시만
**신규:** 게시판 (문의 작성 + 목록 + 답변)

```
[문의하기 페이지 (contact.html)]
│
├── [문의 작성 폼] (.inquiry-form)
│   ├── 닉네임 * (input text, 최대 20자)
│   ├── 제목 *   (input text, 최대 100자)
│   ├── 내용 *   (textarea, 최대 2000자)
│   ├── 관련 정보 (선택)
│   │   ├── 과목 (select: 재정학, 세법학개론 ...)
│   │   ├── 연도 (input number)
│   │   └── 문제 번호 (input number)
│   └── [문의 등록] 버튼
│
├── [관리자 로그인 패널] (.admin-panel) — 숨김 상태
│   ├── 관리자 키 입력 (input password)
│   └── [인증] 버튼 → localStorage 저장
│
└── [문의 목록] (.inquiry-list)
    └── 각 문의 (<details> 펼치기)
        ├── [summary] 제목 | 닉네임 | 날짜 | 답변수 | [답변완료] 배지
        └── [content]
            ├── 문의 본문
            ├── [답변 목록]
            │   └── 각 답변: 닉네임 | 날짜 + 내용
            │       (is_admin=true → "관리자" 배지 + 강조 스타일)
            └── [관리자 전용] 답변 작성 폼
                ├── 내용 (textarea)
                └── [답변 등록] 버튼
```

### 8-2. 관리자 인증 흐름

```
URL: contact.html?admin=1
  ↓
숨겨진 관리자 패널 노출
  ↓
INQUIRY_ADMIN_KEY 입력 → [인증] 클릭
  ↓
localStorage.setItem("inquiry:admin-key", enteredKey)
  ↓
각 문의에 "답변 작성" 폼 노출
  ↓
답변 등록 → POST /api/inquiry/replies
  헤더: X-Inquiry-Admin-Key: {저장된 키}
  ↓
Workers에서 키 검증 → Supabase service_role로 INSERT
  is_admin = true, nickname = "도로파파 (관리자)"
```

### 8-3. contact.js 핵심 구조 (qa.js 패턴 재활용)

```javascript
const state = {
  isAdmin: false,
  adminKey: "",
  posts: [],
};

// 관리자 키 복원
const savedKey = localStorage.getItem("inquiry:admin-key");
if (savedKey) { state.adminKey = savedKey; state.isAdmin = true; }

// URL ?admin=1 진입 시 관리자 패널 노출
if (new URLSearchParams(location.search).get("admin") === "1") {
  showAdminPanel();
}

// 문의 목록 로드
async function loadPosts() { ... fetch("/api/inquiry/posts") ... }

// 답변 등록 (관리자)
async function submitReply(inquiryId, body) {
  await fetch("/api/inquiry/replies", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Inquiry-Admin-Key": state.adminKey,
    },
    body: JSON.stringify({ inquiry_id: inquiryId, nickname: "도로파파", body }),
  });
}
```

---

## 9. 개발자(관리자) 워크플로우

### 방법 1: Supabase Dashboard (빠른 확인)

1. `app.supabase.com` → 프로젝트 선택
2. **Table Editor** → `inquiries` 테이블 확인
3. 새 문의 행 클릭 → 내용 확인
4. **Table Editor** → `inquiry_replies` 테이블 → **Insert row**
   - `inquiry_id`: 해당 문의 id
   - `is_admin`: `true`
   - `nickname`: `도로파파 (관리자)`
   - `body`: 답변 내용

### 방법 2: 관리자 페이지 (브라우저)

1. `https://tax-exam3.pages.dev/contact.html?admin=1` 접속
2. 관리자 키 입력 → 인증
3. 각 문의 펼치기 → 답변 작성 폼에 내용 입력 → [답변 등록]

### 새 문의 알림 (선택 설정)

```
Supabase Dashboard → Database → Webhooks → Create Webhook
  테이블: inquiries
  이벤트: INSERT
  URL: https://hooks.zapier.com/... (또는 Make.com webhook URL)
  → 이메일 알림 또는 카카오/슬랙 메시지 발송
```

---

## 10. 새 배포 파이프라인

```
[로컬 개발]
  git push origin main
        ↓
[GitHub → Cloudflare Pages 자동 빌드]
  - webapp/ 폴더 → 정적 자산으로 배포
  - webapp/functions/ 폴더 → Workers로 자동 배포
        ↓
[배포 완료]
  https://tax-exam3.pages.dev           (정적)
  https://tax-exam3.pages.dev/api/*     (Workers API)

[로컬 테스트]
  wrangler pages dev webapp --d1=DB:tax-exam3-db
  → http://localhost:8788
```

**기존 Render 종료 절차 (마이그레이션 검증 후):**
1. CF Pages에서 전체 기능 동작 확인
2. Render 대시보드 → 서비스 삭제
3. 프로젝트에서 `Dockerfile`, `render.yaml` 삭제 또는 보관

---

## 11. 마이그레이션 단계별 실행 계획

### Phase 1: Cloudflare 환경 셋업

```
1. Cloudflare 계정 생성 (cloudflare.com)
2. GitHub 저장소를 Cloudflare Pages에 연결
   Pages → Create project → Connect to Git → tax_exam3
   Build output directory: webapp
3. D1 데이터베이스 생성
   wrangler d1 create tax-exam3-db
4. wrangler.toml 작성 (database_id 기입)
```

### Phase 2: D1 데이터 마이그레이션

```
5. questions.db → 테이블별 SQL dump 생성
6. wrangler d1 execute --remote로 D1에 import
7. Workers Functions 작성 (Python API → JS 변환)
   - functions/api/questions.js
   - functions/api/ox/questions.js
   - functions/api/notices.js
   - functions/api/health.js
8. wrangler pages dev로 로컬 테스트
```

### Phase 3: Supabase 게시판 셋업

```
9.  Supabase 프로젝트 생성 (app.supabase.com)
10. SQL Editor에서 테이블 생성 (섹션 6 SQL 실행)
11. RLS 정책 설정
12. API Keys 페이지에서 URL + anon key + service_role key 복사
13. Cloudflare Pages 환경변수에 Supabase 정보 입력
```

### Phase 4: 문의하기 게시판 개발

```
14. contact.html → 게시판 UI로 전면 개편
15. contact.js → 게시판 로직 작성 (qa.js 코드 구조 재활용)
16. functions/api/inquiry/posts.js 작성
17. functions/api/inquiry/replies.js 작성
18. functions/api/_middleware.js (CORS) 작성
19. 로컬에서 문의 작성 → 답변 작성 흐름 검증
```

### Phase 5: 배포 전환 및 Render 종료

```
20. CF Pages 환경변수 전체 설정
21. git push → 자동 배포 확인
22. 전체 기능 점검
    - 모의고사 / OX 모드 / 게임 모드 (D1)
    - 공지사항 (D1)
    - 문의하기 게시판 (Supabase)
    - 오답노트 (localStorage, 서버 불필요)
23. Render 서비스 삭제
24. Dockerfile, render.yaml 삭제 커밋
```

---

## 12. 주요 파일 변경 요약

| 파일 | 변경 내용 |
|------|-----------|
| [webapp/contact.html](webapp/contact.html) | 이메일 페이지 → 게시판 UI로 전면 개편 |
| [webapp/contact.js](webapp/contact.js) | 이메일 로딩 → 게시판 CRUD 로직으로 교체 |
| [webapp/qa.html](webapp/qa.html) | 삭제 또는 contact.html 리디렉션으로 변경 |
| [webapp/qa.js](webapp/qa.js) | 삭제 (contact.js로 통합) |
| webapp/functions/api/*.js | 신규 생성 (Python API → Workers JS) |
| wrangler.toml | 신규 생성 |
| Dockerfile | 삭제 예정 |
| render.yaml | 삭제 예정 |

---

## 13. 비용 예상 (무료 티어 기준)

| 서비스 | 예상 사용량 | 무료 한도 | 비용 |
|--------|-----------|-----------|------|
| Cloudflare Pages | 정적 파일 서빙 | 무제한 | 무료 |
| Cloudflare Workers | API 요청 (학습자 소수) | 100k req/day | 무료 |
| Cloudflare D1 | 기출문제 읽기 | 25M read/day | 무료 |
| Supabase | 게시판 DB | 500MB, API 무제한 | 무료 |
| **합계** | | | **$0/월** |

> Render 무료 플랜은 비활성 시 15분 후 슬립(콜드 스타트 지연)이 있었으나,
> Cloudflare Pages/Workers는 항상 활성 상태로 지연 없음.
