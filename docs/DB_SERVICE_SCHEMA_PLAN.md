# 서비스 DB 분리 계획 (배포용)

## 1) 분리 원칙
- 개발/운영 배치(수집, 현행화, 해설 생성)와 사용자 서비스(문제풀이, OX, 즐겨찾기, 통계)는 DB를 분리한다.
- 배포 DB에는 서비스 조회/저장에 필요한 테이블만 둔다.
- 연도 확장(2026+, 2027+)은 **테이블 분리 대신 `exam_year` 컬럼 + 인덱스**로 처리한다.

## 2) 연도별 테이블 분리 여부
- 결론: `exam_questions_2025`, `exam_questions_2026`처럼 연도별 테이블 분리는 권장하지 않는다.
- 이유:
  - 쿼리/인덱스/코드 복잡도 증가
  - 연도별 UNION 필요
  - 마이그레이션/백업 정책 관리 부담 증가
  - 서비스 기능(연도 필터, 통합 통계)에 불리
- 권장: 단일 테이블 + `exam_year` 인덱스 전략

## 3) 배포용 최소 스키마
- 콘텐츠
  - `exam_question_bank`
  - `exam_choice_ox_bank`
- 사용자 런타임
  - `app_users`
  - `user_choice_visibility`
  - `user_exam_attempts`
  - `user_exam_attempt_answers`
  - `user_subject_recent_scores`
  - `bank_user_favorites`
  - `bank_user_notes` (향후 확장 대비 최소 유지)

## 4) 개발용 스키마와의 관계
- `SQLiteRepository(schema_profile="full")`: 기존 개발/배치 전체 스키마
- `SQLiteRepository(schema_profile="service")`: 배포용 최소 스키마
- 웹앱은 `service` 프로파일을 사용한다.

## 5) 배포용 DB 생성 절차
1. 로컬 개발 DB(`tax_exam.db`)에서 최신 콘텐츠 확보
2. 아래 명령으로 서비스 DB 생성
   - `python -m tax_exam_app.build_service_db --source-db tax_exam.db --target-db tax_exam_service.db`
3. 생성된 `tax_exam_service.db`만 배포 이미지에 포함

## 6) 운영 포인트
- 배포 재생성 시 사용자 데이터가 초기화될 수 있으므로 운영 정책을 명확히 한다.
- 사용자 데이터 유지가 필요해지면 SQLite에서 Postgres 전환을 우선 검토한다.
