# 프로젝트 현황 문서

> 작성일: 2026-03-05
> 대상: tax_exam3 — "OX가 답이다 (세무사편)"

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 앱명 | OX가 답이다 (세무사편) |
| 목적 | 세무사 1차 시험 대비 웹 학습 플랫폼 |
| 개발자 | 도로파파 (rian4u@naver.com) |
| 프론트엔드 | HTML5 + ES6 JavaScript + CSS3 |
| 백엔드 | Python 3.12 (`http.server.ThreadingHTTPServer`) |
| 데이터베이스 | SQLite3 (`data/questions.db`, 43MB) |
| 배포 | Docker + Render (main 브랜치 push 시 자동배포) |
| 로컬 실행 | `python webapp/server.py --host 127.0.0.1 --port 8000` |

---

## 2. 아키텍처

```
┌────────────────────────────────────────────┐
│  HTML / CSS / JavaScript (프론트엔드)       │
│  index.html, mock-exam.js, game.js, ...    │
└────────────────┬───────────────────────────┘
                 │ REST API (JSON)
┌────────────────▼───────────────────────────┐
│  Python HTTP 서버 (webapp/server.py)        │
│  ThreadingHTTPServer + sqlite3 직접 쿼리   │
└────────────────┬───────────────────────────┘
                 │ sqlite3
┌────────────────▼───────────────────────────┐
│  SQLite 데이터베이스 (data/questions.db)    │
│  문제 / OX / 오답노트 / 공지게시판         │
└────────────────────────────────────────────┘
```

---

## 3. 디렉토리 구조

```
tax_exam3/
├── webapp/                          # 웹 애플리케이션 (배포 서빙 루트)
│   ├── server.py                    # HTTP 서버 + REST API (1337줄)
│   ├── index.html                   # 메인 화면 — 6가지 모드 진입점 (102줄)
│   ├── mock-exam.html / .js         # 모의고사 — 5지선다 기출 (963줄)
│   ├── ox-mode.html / .js           # OX 모드 — OX 순차 풀이 (695줄)
│   ├── game.html / .js              # 게임 모드 — OX 낙하 게임 (1002줄)
│   ├── wrong-note.html / .js        # 오답 관리 — 로컬 저장소 검색 (252줄)
│   ├── notice.html / .js            # 공지사항 — 관리자 모드 포함 (183줄)
│   ├── contact.html / .js           # 문의하기 — 이메일 연결 (40줄)
│   ├── qa.html / .js                # Q&A — 현재 서비스 중단 (290줄)
│   ├── local-user-data.js           # localStorage 오답노트 API (270줄)
│   ├── skin.js                      # 3가지 UI 테마 전환 (75줄)
│   ├── styles.css                   # 공통 스타일 + 3 스킨 정의 (3026줄)
│   └── game.css                     # 게임 전용 스타일 (226줄)
│
├── data/
│   ├── questions.db                 # SQLite DB (43MB) — 핵심 데이터
│   ├── OX문제/                      # 과목별 OX 텍스트 (10개 파일)
│   │   ├── 재정학ox.txt (916줄)
│   │   ├── 상법ox.txt (808줄)
│   │   ├── 회계학개론.txt (560줄)
│   │   ├── 법인세법.txt (404줄)
│   │   ├── 국세기본법.txt (307줄)
│   │   ├── 국세징수법.txt (204줄)
│   │   ├── 부가가치세법.txt (204줄)
│   │   ├── 소득세법.txt (203줄)
│   │   ├── 행정소송법ox.txt (203줄)
│   │   └── 조세범처벌법.txt (101줄)
│   ├── 2025/
│   │   ├── 원본문제/                # 기출 PDF (5개 파일)
│   │   ├── 풀이/                   # 과목별 풀이 TXT
│   │   └── 실제정답.txt            # 공식 배포 정답
│   ├── 2024/ (동일 구조)
│   └── 2023/ (동일 구조)
│
├── scripts/
│   ├── load_2025_questions.py       # PDF → DB 문항 파싱·적재 (1175줄)
│   ├── import_ox_text.py            # OX 텍스트 → DB 적재 (293줄)
│   ├── import_solution_text.py      # 풀이 텍스트 → 정답/해설 업데이트 (149줄)
│   ├── sync_distributed_answers.py  # 공식 배포정답 동기화 (149줄)
│   └── data_paths.py                # 파일 경로 해석 유틸리티 (94줄)
│
├── Dockerfile                       # python:3.12-slim, webapp/ + questions.db만 포함
├── render.yaml                      # Render 자동배포 설정
└── README.md                        # 기존 README
```

---

## 4. 데이터베이스 스키마

| 테이블 | 주요 컬럼 | 용도 |
|--------|-----------|------|
| `문제` | 출제연도, 과목, 문제번호, 문제지문, 보기_1~5, 답, 답_배포, 해설, 렌더링 마크업 | 5지선다형 기출문제 |
| `OX` | 출제연도, 과목, 문제번호, stable_id, 문제, 답(O/X), 해설 | OX 문제 |
| `오답노트` | question_key, 중요도, 코멘트, 수정일시, user_id | 서버측 오답 기록 (레거시) |
| `공지게시판` | 제목, 본문, 작성일, published | 공지사항 |
| `qa_posts`, `qa_answers` | — | Q&A (현재 비활성화) |
| `app_meta` | — | 앱 메타데이터 |

**`문제.답` vs `문제.답_배포`**
`답`은 풀이 텍스트에서 파싱한 정답, `답_배포`는 공식 배포 정답지(`실제정답.txt`)에서 동기화한 정답. 불일치 시 `답_배포`를 우선 사용.

---

## 5. REST API

서버(`webapp/server.py`)는 정적 파일 서빙과 JSON API를 통합 제공한다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/health` | 서버 상태 확인 |
| GET | `/api/questions?year=&subject=&user_id=` | 기출 5지선다 문제 목록 |
| GET | `/api/ox/questions?year=&subject=` | OX 문제 목록 |
| GET | `/api/notices` | 공지사항 목록 |
| POST | `/api/notices` | 공지 등록 (X-Notice-Admin-Key 헤더 필요) |
| GET | `/api/contact` | 연락처 정보 |
| * | `/api/wrong-note/*` | 오답노트 CRUD (서버측, 레거시 — 현재 클라이언트 localStorage로 대체) |

**API 서버 자동 탐색 순서 (클라이언트):**
1. `window.location.origin`
2. `http://{hostname}:8000`
3. `http://127.0.0.1:8000`
4. `http://localhost:8000`

---

## 6. 시험 과목 구성

### 1교시 (80문항)
| 번호 | 과목 |
|------|------|
| 1~40 | 재정학 |
| 41~80 | 세법학개론 |

### 2교시 (80문항)
| 번호 | 과목 |
|------|------|
| 1~40 | 회계학개론 |
| 41~80 | 상법 / 민법 / 행정소송법 (선택 1개) |

### OX 전용 과목 (5지선다 기출 없음)
국세기본법, 국세징수법, 법인세법, 부가가치세법, 소득세법, 조세범처벌법

---

## 7. 학습 모드 상세

### 7.1 모의고사 (`mock-exam.js`)

- 과목 + 연도 선택 → 40문항 5지선다 순차 풀이
- **상태 그리드**: 40칸, 정답(초록) / 오답(빨강) / 미풀이 색상 표시
- **신호등 태그**: red / yellow / green / gray (중요도 표시)
- **코멘트 팝업**: 오답노트 메모 입력
- **해설 팝업**: MathJax 수식 렌더링 지원
- **내장 계산기**: M+, M-, MR, MC, GT 메모리 기능
- **URL 파라미터**: `?subject=&year=&no=` (특정 문제 직접 진입 가능)

```javascript
// 핵심 상태 구조
const state = {
  selectedSubject, selectedYear, userId,
  questions: [],      // API에서 로드한 문제 목록
  currentIndex: 0,
  answers: {},        // {문제번호: 선택지}
  wrongNotes: {},     // localStorage 오답노트
  calc: {...},        // 계산기 상태
};
```

### 7.2 OX 모드 (`ox-mode.js`)

- 과목 선택 → OX 문제 순차 풀이
- **중요도 필터**: 활성화된 신호등 색상의 문제만 출제
- **복습 패널**: 풀이 완료 후 전체 정오답 목록 표시
- **해설 팝업** + 신호등 태그 동시 지원

### 7.3 게임 모드 (`game.js`)

- OX 문제가 블록으로 낙하 (블록당 10초 제한)
- **조작**: 좌 스와이프 = O, 우 스와이프 = X
- **생명 시스템**: 3개 (❤❤❤), 오답/시간초과 시 감소
- **점수/콤보**: 정답 100점, 콤보 5회 이상 시 2배
- **마일스톤**: 20점("합격권 진입!"), 50점("집중력 최고조!"), 100점("실전 감각 완성!")
- **오디오**: Web Audio API (정답: 조화음, 오답: 불협화음)
- **게임오버 후**: 복습 해설 패널 표시

### 7.4 오답 관리 (`wrong-note.js`)

- localStorage 기반 오답노트 실시간 검색
- **필터**: 과목 드롭다운 + 키워드 입력 + 중요도 신호등 (120ms 디바운싱)
- OX 문제: 인라인 해설 표시
- 기출 문제: `mock-exam.html?subject=&year=&no=` 링크로 이동
- `storage` 이벤트로 다른 탭 변경사항 자동 반영

---

## 8. 로컬 데이터 저장 구조

오답노트는 서버 없이 **localStorage**에 저장된다 (레거시 서버 API 대체).

```javascript
// 키: "taxexam:user-notes:v1"
{
  version: 1,
  updated_at: "ISO datetime",
  notes: {
    // 복합 키: "{source}|{year}|{subject}|{question_key}"
    "ox|2025|재정학|ox-001-abc123": {
      source: "ox",          // "ox" | "mock"
      year: 2025,
      subject: "재정학",
      question_key: "ox-001-abc123",   // stableId (OX) 또는 문제번호 (기출)
      importance: "red",               // "red"|"yellow"|"green"|"gray"|""
      comment: "사용자 메모",          // 최대 4000자
      explanation: "해설",             // 최대 8000자
      question_preview: "문제 미리보기",
      answer: "O",
      updated_at: "ISO datetime"
    }
  }
}
```

| localStorage 키 | 용도 |
|----------------|------|
| `taxexam:user-notes:v1` | 오답노트 메인 저장소 |
| `taxexam:user-notes:v1:backup` | 백업 (이중 저장) |
| `taxexam:device-id` | 기기 고유 ID (UUID, 자동 생성) |
| `taxDoldolSkin` | 스킨 설정 (1/2/3) |

---

## 9. UI 테마 시스템

CSS 변수 기반 3가지 스킨. `skin.js`가 `body` 클래스를 `.skin-1 / .skin-2 / .skin-3`으로 전환.

| 스킨 | 이름 | 배경 | 액센트 | 폰트 |
|------|------|------|--------|------|
| 1 (기본) | Dark | 진한 파란색 `#0a1528` | `#3fd7ff` (시안) | Exo 2 |
| 2 | Light | 밝은 흰색 계열 | `#00a2d8` | Manrope |
| 3 | Green | 연녹색 | `#7ecb8c` | Noto Sans KR |

공통 CSS 변수: `--primary`, `--danger`, `--ok`, `--bg-*`, `--text-*` 등

---

## 10. 배포 파이프라인

```
[개발] main 브랜치에 push
          ↓
[Render] render.yaml의 autoDeploy: true 감지
          ↓
[Docker] python:3.12-slim 이미지 빌드
         포함: webapp/ 전체 + data/questions.db
         제외: data/2023~2025/, scripts/, config/
          ↓
[실행] python webapp/server.py --host 0.0.0.0 --port $PORT
```

---

## 11. 데이터 적재 파이프라인 (개발 환경)

새 연도 데이터를 DB에 넣는 순서:

```bash
# 1. PDF 원본 → DB 문항 적재
python scripts/load_2025_questions.py --data-root data --years 2025

# 2. 풀이 텍스트 → 정답 + 해설 업데이트
python scripts/import_solution_text.py \
  --db-path data/questions.db --year 2025 --subject 재정학

# 3. 공식 정답지 → 배포정답(답_배포) 동기화
python scripts/sync_distributed_answers.py \
  --db-path data/questions.db --data-root data

# 4. OX 텍스트 → OX 테이블 적재
python scripts/import_ox_text.py \
  --db-path data/questions.db --year 2025 --subject 재정학
```

---

## 12. 현재 상태

### 완성된 기능
- 2025년 기출 모의고사 (재정학, 세법학개론, 회계학개론, 상법, 민법, 행정소송법)
- OX 모드 (10개 과목)
- 게임 모드
- 오답 관리 (localStorage 기반, 서버 불필요)
- 공지사항 (관리자 등록 포함)
- 3가지 UI 스킨

### 제약 및 미완성 사항

| 항목 | 상태 |
|------|------|
| 2024년 이전 데이터 | 일부 과목 풀이/해설 미완성 |
| 로그인 | 없음 (기기 ID 기반 게스트 전용) |
| Q&A 기능 | 서비스 중단 (`qa.html` 코드는 유지) |
| MathJax | CDN 의존 — 오프라인 시 수식 렌더링 불가 |
| 두문자 관리 | 미구현 |

### 데이터 규모
- 기출문제: 2023~2025년 × 160문항 = 약 **480문항**
- OX 문제: 10개 과목 × 평균 100~300문제 = 약 **3,000+ 문제**
- DB 크기: **43MB**

---

## 13. 주요 파일 빠른 참조

| 파일 | 역할 | 분량 |
|------|------|------|
| [webapp/server.py](webapp/server.py) | HTTP 서버 + 전체 REST API | 1337줄 |
| [webapp/index.html](webapp/index.html) | 메인 홈 화면 | 102줄 |
| [webapp/mock-exam.js](webapp/mock-exam.js) | 모의고사 핵심 로직 | 963줄 |
| [webapp/ox-mode.js](webapp/ox-mode.js) | OX 풀이 로직 | 695줄 |
| [webapp/game.js](webapp/game.js) | 낙하 게임 엔진 | 1002줄 |
| [webapp/wrong-note.js](webapp/wrong-note.js) | 오답노트 검색 | 252줄 |
| [webapp/local-user-data.js](webapp/local-user-data.js) | localStorage 오답노트 API | 270줄 |
| [webapp/skin.js](webapp/skin.js) | 스킨 전환 | 75줄 |
| [webapp/styles.css](webapp/styles.css) | 공통 스타일 + 3 스킨 | 3026줄 |
| [webapp/game.css](webapp/game.css) | 게임 전용 스타일 | 226줄 |
| [scripts/load_2025_questions.py](scripts/load_2025_questions.py) | PDF 파싱 + DB 적재 | 1175줄 |
| [scripts/import_ox_text.py](scripts/import_ox_text.py) | OX 텍스트 DB 적재 | 293줄 |
| [scripts/import_solution_text.py](scripts/import_solution_text.py) | 풀이 텍스트 DB 업데이트 | 149줄 |
| [scripts/sync_distributed_answers.py](scripts/sync_distributed_answers.py) | 배포정답 동기화 | 149줄 |
| [scripts/data_paths.py](scripts/data_paths.py) | 경로 해석 유틸리티 | 94줄 |
| [data/questions.db](data/questions.db) | SQLite 메인 DB | 43MB |
