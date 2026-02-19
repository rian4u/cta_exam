# Tax Exam App 인수인계 문서 (2026-02-18, Schema v2)

## 1) 목표
- 세무사 1차 기출 서비스
- 핵심 데이터: 연도별 문제/보기/정답, 보기별 OX 전환, 해설, 사용자별 즐겨찾기/보기가리기/최근점수

## 2) 현재 구조 요약
- 백엔드: FastAPI (`src/tax_exam_app/web.py`)
- 저장소: SQLite (`src/tax_exam_app/repository.py`)
- 프론트: Vanilla JS (`src/tax_exam_app/static/app.js`)
- DB: `tax_exam.db`

## 3) 스키마 검토 결론
기존 스키마는 `문제은행 + OX지문 + 즐겨찾기`는 처리 가능했지만, 아래 사용자 상태를 장기적으로 관리하기엔 부족했다.
- 사용자 엔티티 부재
- 보기 가리기 상태 영속화 부재
- 시험 시도(Attempt) 이력/정답 로그 부재
- 과목별 최근점수 집계 테이블 부재

따라서 Schema v2로 확장했다.

## 4) Schema v2 (신규/핵심)
### 4-1. 컨텐츠 테이블
- `exam_question_bank`: 문제/보기/정답/해설
- `exam_choice_ox_bank`: 보기별 OX 적합성 + expected OX
- `exam_explanation_history`: 해설 이력

### 4-2. 사용자 테이블 (신규)
- `app_users`
  - `user_id` PK
  - `display_name`, `created_at`, `updated_at`

- `user_choice_visibility`
  - 사용자별 보기 가리기 상태
  - PK 제약: `(user_id, exam_year, subject_code, question_no_exam, choice_no)`
  - `hidden`(0/1), `updated_at`

- `user_exam_attempts`
  - 모의고사/OX 제출 단위 이력
  - `mode`, `exam_year(nullable for ox-all-years)`, `subject_code`
  - `total_questions`, `answered_questions`, `correct_count`, `score_100`, `duration_seconds`
  - `started_at`, `finished_at`

- `user_exam_attempt_answers`
  - 시도별 문항 응답 로그
  - mock: `question_bank_id` 사용
  - ox: `ox_item_id` 사용
  - `selected_answer`, `correct_answer`, `is_correct`

- `user_subject_recent_scores`
  - 사용자/과목/모드별 최신점수 캐시
  - PK: `(user_id, subject_code, mode)`
  - `last_attempt_id`, `last_exam_year`, `last_score_100`, `attempts_count`, `updated_at`

### 4-3. 기존 사용자 테이블 유지
- `bank_user_favorites`: 문제 단위 컬러 즐겨찾기
- `bank_user_notes`: 노트/상태 메모

## 5) API 변경사항
### 5-1. 사용자/상태
- `POST /api/users/upsert`
- `GET /api/users/{user_id}/subject-recent-scores`
- `GET /api/choice-visibility?user_id&exam_year&subject_code`
- `POST /api/choice-visibility`

### 5-2. 제출 API 확장
- `POST /api/mock/submit`
  - 입력: `user_id`, `started_at`, `duration_seconds` 추가
  - 처리: attempt + answer log + recent score 저장
  - 출력: `attempt_id`, `score_100` 추가

- `POST /api/ox/submit`
  - 동일하게 `attempt_id`, `score_100` 반환/저장

## 6) 프론트 반영
- 사용자 식별자 상수 사용: `CURRENT_USER_ID = "local-user"`
- 시작 시 `POST /api/users/upsert` 호출
- 보기 가리기 토글 시 `POST /api/choice-visibility` 저장
- 모의고사 시작 시 `GET /api/choice-visibility`를 불러와 기존 숨김 상태 복원
- 채점 시 제출 payload에 `user_id`, `started_at`, `duration_seconds` 포함

## 7) 데이터 정합성 관점
요청사항 충족 여부:
- 연도별 문제/보기/해설: 충족 (`exam_question_bank`)
- 보기 OX화 및 판정근거: 충족 (`exam_choice_ox_bank`)
- 사용자별 즐겨찾기: 충족 (`bank_user_favorites`)
- 사용자별 보기 비가시화 상태: 충족 (`user_choice_visibility`)
- 사용자별 과목별 최근점수: 충족 (`user_subject_recent_scores` + attempt log)

## 8) 운영 포인트
- 현재는 `local-user` 단일 사용자로 동작하나, `user_id` 파라미터가 API 전반에 반영되어 앱 로그인 연동 시 그대로 확장 가능
- 앱 배포 시 권장:
  - 인증 토큰 기반 user_id 매핑
  - 서버 DB를 PostgreSQL로 이전
  - attempt/answer 로그 아카이빙 정책 수립

## 9) 실행
```powershell
$env:PYTHONPATH='src'
python -m uvicorn tax_exam_app.web:app --host 127.0.0.1 --port 8001
```
