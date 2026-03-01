# scripts

데이터 적재, 동기화, 검증을 담당하는 유틸리티 스크립트 모음입니다.

## 권장 실행 순서

1. PDF 문제 적재
   - [load_pdf_questions.py](/e:/Project/tax_exam3/scripts/load_pdf_questions.py)
   - 여러 연도 공통용 로더
2. 2025 전용 원본 적재(구형/상세 파서)
   - [load_2025_questions.py](/e:/Project/tax_exam3/scripts/load_2025_questions.py)
3. 풀이 텍스트 적재
   - [import_solution_text.py](/e:/Project/tax_exam3/scripts/import_solution_text.py)
4. 배포답안 반영
   - [sync_distributed_answers.py](/e:/Project/tax_exam3/scripts/sync_distributed_answers.py)
5. OX 텍스트 적재
   - [import_ox_text.py](/e:/Project/tax_exam3/scripts/import_ox_text.py)

## 파일별 역할

- [data_paths.py](/e:/Project/tax_exam3/scripts/data_paths.py)
  - 연도별 `문제/원본문제/풀이/OX문제` 경로 해석 공통 모듈

- [load_pdf_questions.py](/e:/Project/tax_exam3/scripts/load_pdf_questions.py)
  - 연도별 PDF를 순회하며 문제 테이블 적재
  - 현재 기준 메인 공용 적재 스크립트

- [load_2025_questions.py](/e:/Project/tax_exam3/scripts/load_2025_questions.py)
  - 2025 포맷에 맞춘 상세 파서
  - 레거시 호환과 세부 정제 로직이 많음

- [import_solution_text.py](/e:/Project/tax_exam3/scripts/import_solution_text.py)
  - 과목별 풀이 TXT를 읽어 `답`, `해설`, `답변여부` 반영
  - 적재 직후 `답_배포`와 비교해 일치/불일치 집계 가능

- [sync_distributed_answers.py](/e:/Project/tax_exam3/scripts/sync_distributed_answers.py)
  - `실제정답.txt`를 읽어 `답_배포` 컬럼 동기화

- [extract_published_answers_from_hwp.py](/e:/Project/tax_exam3/scripts/extract_published_answers_from_hwp.py)
  - HWP에서 배포답안 추출을 시도하는 보조 스크립트
  - Gemini 연동을 포함

- [fill_missing_answers_gemini.py](/e:/Project/tax_exam3/scripts/fill_missing_answers_gemini.py)
  - 답/해설이 비어 있는 문제를 배치 단위로 LLM에 요청해 채움

- [revalidate_mismatch_gemini.py](/e:/Project/tax_exam3/scripts/revalidate_mismatch_gemini.py)
  - 풀이 답안과 배포답안 불일치 재검증

- [import_ox_text.py](/e:/Project/tax_exam3/scripts/import_ox_text.py)
  - `data/OX문제` 기반 OX 텍스트를 `OX` 테이블에 반영

- [build_ox_from_questions.py](/e:/Project/tax_exam3/scripts/build_ox_from_questions.py)
  - 객관식 문제/해설 기반 OX 후보 생성용 보조 스크립트

- [load_2025_ox_questions.py](/e:/Project/tax_exam3/scripts/load_2025_ox_questions.py)
  - 구형 OX 적재 스크립트
  - 현재는 [import_ox_text.py](/e:/Project/tax_exam3/scripts/import_ox_text.py) 우선

## 참고

- LLM 연동 스크립트는 API 키가 필요합니다.
- 배포 서비스 런타임에는 대부분 필요하지 않습니다.
- 실서비스 반영 기준은 항상 `data/questions.db`입니다.
