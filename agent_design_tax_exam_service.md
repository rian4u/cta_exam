# agent_design_tax_exam_service.md
## 세무사 1차 기출문제 현행화/문제풀이 서비스 - Codex 에이전트 작업설계서 (v1.2)

---

# 1. 작업 컨텍스트

## 1.1 배경

세무사 1차 시험 기출문제는 매년 누적되며, 세법 개정으로 인해 일부 문항은 현행 법령과 불일치한다.
수험생은 최신 법령 기준으로 정리된 기출 + 해설 + 오답관리 기능을 필요로 한다.

본 시스템은 다음을 자동화한다.
- 기출 수집
- 문제 단위 구조화
- DB 적재
- LLM 기반 현행화 판단
- 문제 수정/버전 관리
- 해설 생성
- 검증 게이트 통과 시 공개
- 오답노트(초기 로컬 저장, 이후 동기화 확장 가능)

---

# 2. 범위 정의

## 2.1 시험 범위
- 시험: 세무사 1차
- 기간: 최근 10개년(초기)
- 과목: 1차 전 과목

## 2.2 데이터 출처/저작권 범위
- 출처 사이트 약관, robots.txt, 저작권 정책을 사전 검토한다.
- 원문 저장은 내부 검증 목적 범위로 제한하며, 외부 공개 데이터는 정책에 맞춘 파생 결과만 제공한다.
- 위반 가능성이 있는 수집 작업은 즉시 중단하고 `legal_hold` 상태로 격리한다.

---

# 3. 전체 에이전트 구조

멀티 에이전트 구조를 사용한다.

| Agent | 역할 |
|------|------|
| A | 수집/원문 저장/중복제거 |
| B | 문제 구조화(JSON 스키마) |
| C | 현행화 판단(법령 근거 수집) |
| D | 문제 수정(버전 생성) |
| E | 해설 생성 |
| F | 검증/공개 게이트 |
| G | DB 적재/버전/배치 관리 |

---

# 4. 워크플로우 정의

## 4.1 단계 1 - 수집 (Agent A)

### 입력
- 연도 범위
- 과목 목록
- 시작 URL 목록

### 처리 (코드)
- 크롤링/파싱
- HTML/PDF 텍스트 추출
- 원문 해시 생성(content_hash)
- 중복 체크(idempotency)

### 출력
- `raw_question` 레코드

### 성공 기준
- 연도 x 과목 x 문항 기준 누락 없음

### 실패 전략
- 네트워크/타임아웃 3회 재시도(지수 백오프)
- CAPTCHA/차단 발생 시 `blocked_source`로 격리
- 약관 위반 의심 시 `legal_hold`로 즉시 중단

---

## 4.2 단계 2 - 문제 구조화 (Agent B)

### 입력
- raw 텍스트

### 처리 (LLM + 규칙 기반)
- 문제/보기/정답 분리
- 과목/연도/문항번호 매핑
- 파싱 실패 시 규칙 기반 fallback 수행

### 출력 스키마

```json
{
  "exam_stage": "1st",
  "exam_year": 2025,
  "subject_code": "TAX_LAW_1",
  "question_no": 1,
  "question_text": "",
  "choices": ["", "", "", "", ""],
  "answer_key": "2"
}
```

### 검증
- JSON schema validation
- 보기 개수(기본 5) 검증
- 정답 존재 여부 검증

### 실패 처리
- 스키마 오류 2회 재시도 후 `quarantine` 큐로 이동

---

## 4.3 단계 3 - 현행화 판단 (Agent C)

### 입력
- 구조화된 문제

### 처리 (LLM + 웹검색)
- 법령 키워드 추출
- 신뢰 가능한 출처에서 최신 조문 조회
- 원문 대비 변경 가능성 판단

### 법령 출처 화이트리스트(초기)
- 국가법령정보센터
- 국세청
- 기획재정부(세제 관련 고시/보도)

### 출력

```json
{
  "needs_update": true,
  "reason": "",
  "legal_refs": [
    {
      "law_name": "",
      "article": "",
      "reference_url": "",
      "as_of_date": "2026-02-16"
    }
  ],
  "confidence": "high"
}
```

### 성공 기준
- `legal_refs` 1개 이상 + `as_of_date` 필수
- 또는 근거 부족 시 `confidence=low` 명시

---

## 4.4 단계 4 - 문제 수정 (Agent D)

조건: `needs_update = true`

### 처리 (LLM)
- 기존 형식/난이도 유지
- 수치/조건/용어를 최신 법령 기준으로 업데이트
- 변경 요약(`change_summary`) 생성

### 출력
- 신규 버전 생성(`question_versions`)
- 원본은 immutable로 보존

---

## 4.5 단계 5 - 해설 생성 (Agent E)

### 처리 (LLM)
- 정답 풀이 과정
- 오답 소거 논리
- 관련 법령/조문/근거 인용

### 검증
- 해설 결론과 `answer_key` 일치
- 근거 누락 시 `needs_human_review=true`

---

## 4.6 단계 6 - 검증/공개 게이트 (Agent F)

### 공개 게이트 규칙
- `confidence=high|medium` + 근거 URL 존재 시 공개 가능
- `confidence=low` 또는 근거 없음 -> `review_required`
- 스키마/정합성 오류 존재 시 공개 금지

### 처리 (코드)
- `status`를 `draft/review_required/published` 중 하나로 확정
- 검색 인덱싱은 `published`만 수행

---

## 4.7 단계 7 - DB 적재/배치 정리 (Agent G)

### 처리 (코드)
- 트랜잭션 단위 저장
- 배치 실행 로그/카운트 업데이트
- 재처리 가능하도록 idempotency key 유지

---

# 5. 데이터 구조

## 5.1 questions
- id
- exam_stage
- exam_year
- subject_code
- question_no
- question_text
- choices(jsonb)
- answer_key
- explanation_text
- updated_flag
- legal_refs(jsonb)
- confidence
- needs_human_review
- content_hash
- source_url
- status (`draft|review_required|published|legal_hold`)
- created_at
- updated_at

## 5.2 question_versions
- id
- question_id
- version_no
- question_text
- choices
- answer_key
- explanation_text
- change_summary
- created_at

## 5.3 batch_runs
- id
- mode (`collect_only|collect_and_process|reprocess_existing`)
- params(jsonb)
- status (`running|partial_success|success|failed`)
- started_at
- finished_at
- counts(jsonb)
- logs_path

## 5.4 user_notes (확장형)
- id
- user_id(nullable: 로컬 모드)
- question_id
- state (`wrong|unsure|bookmark|review`)
- memo
- tags(jsonb)
- source (`local|cloud`)
- created_at
- updated_at
- last_reviewed_at

## 5.5 사용자 상태/학습이력 (모바일 앱 배포 대비)
- `app_users`
  - user_id(pk), display_name, created_at, updated_at
- `user_choice_visibility`
  - user_id, exam_year, subject_code, question_no_exam, choice_no, hidden, updated_at
  - 사용자가 특정 보기(지문)를 가려둔 상태를 영속 저장
- `user_exam_attempts`
  - user_id, mode(mock|ox), exam_year(nullable), subject_code
  - total_questions, answered_questions, correct_count, score_100
  - started_at, finished_at, duration_seconds
- `user_exam_attempt_answers`
  - attempt_id, item_kind(question|ox_item), question_bank_id/ox_item_id
  - selected_answer, correct_answer, is_correct
  - 사용자 응답 로그(재현/분석/리포트용)
- `user_subject_recent_scores`
  - user_id, subject_code, mode, last_attempt_id, last_exam_year, last_score_100, attempts_count, updated_at
  - 사용자 과목별 최근 성적 캐시

설계 원칙:
- 컨텐츠 테이블과 사용자 상태 테이블을 분리한다.
- 제출 시점에 시도/응답 로그를 저장하고, 최근 점수 캐시를 원자적으로 갱신한다.
- 로컬 사용자(`local-user`)와 인증 사용자 모두 동일 스키마를 사용한다.

---

# 6. 배치 실행 정책

- 정기 스케줄: 초기 미적용(수동 실행)
- 운영 안정화 후 정기 실행(예: 월 1회) 전환
- 연 1회 시험 공개 시점 재처리 배치 실행

모드:
- `collect_only`
- `collect_and_process`
- `reprocess_existing`

운영 규칙:
- 동일 파라미터 중복 실행 잠금
- 실패 건은 DLQ(격리 큐) 저장
- 부분 성공 시 `partial_success`로 종료

---

# 7. LLM vs 코드 책임 분리

## LLM 영역
- 구조화
- 현행화 판단
- 문제 수정
- 해설 생성
- 자기검증(형식/논리)

## 코드 영역
- 크롤링/파싱
- DB 저장/버전 관리
- 배치 오케스트레이션
- 공개 게이트 강제
- API 응답/로깅/모니터링

---

# 8. 실패 처리 전략

| 유형 | 전략 |
|------|------|
| 네트워크 오류 | 3회 재시도 + backoff |
| 스키마 오류 | 2회 재시도 후 격리 |
| 근거 부족 | confidence=low + review_required |
| 법적 리스크 | legal_hold + 관리자 확인 |
| 부분 실패 | batch_run partial_success |

---

# 9. 오답노트/수익모델 확장 정책

## 9.1 오답노트 저장
- Web: IndexedDB
- Mobile: AsyncStorage 또는 SQLite
- 초기: 로그인 없이 로컬 저장

## 9.2 향후 구독 확장 대비
- `user_id`, `source(local|cloud)` 필드 선반영
- 동기화 충돌 규칙: `updated_at` 기준 최신 우선 + 수동 병합 옵션

## 9.3 수익모델(후속)
- 광고형: 무료 풀이 + 광고 노출
- 구독형: 클라우드 동기화, 심화 해설, 약점 분석
- 기능 플래그로 무료/유료 기능 제어

---

# 10. 보안 및 리스크

- 수집 출처의 약관/저작권/접근정책 검토 필수
- 법령 근거 URL, `as_of_date` 저장 의무
- 근거 불충분 결과는 공개 제한
- 민감 데이터 최소 수집 원칙 준수

---

# 11. 수용 기준

- 최근 10개년 x 1차 전 과목 수집 완료
- 문항 단위 end-to-end 자동 처리 성공
- 공개 게이트 정책대로 상태 분기 동작
- 근거/버전/로그 추적 가능
- 오답노트 로컬 저장 및 추후 동기화 확장 가능성 확인

---

# 12. 절대 포함하지 말 것

- 상세 프롬프트 원문
- 운영 비밀키/인증정보
- 무단 재배포 가능한 원문 덤프

---

# 문서 상태

v1.2 (2026-02-18)
Codex 구현 진행 중
