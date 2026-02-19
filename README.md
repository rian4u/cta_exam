﻿# 세무사 돌돌이

세무사 1차 기출문제 수집/현행화/해설/오답노트를 위한 멀티 에이전트 서비스입니다.

## 구현된 에이전트 (A-G)
- A `CollectorAgent`: 원문 수집(현재 스텁, 실크롤러 교체 지점)
- B `StructurerAgent`: raw 텍스트를 문제 스키마로 구조화
- C `UpdateJudgeAgent`: 현행화 필요 여부/법령 근거/신뢰도 산정
- D `ReviserAgent`: 필요 시 문제 문안 수정 + 변경요약 생성
- E `ExplainerAgent`: 정답/오답 논리 해설 생성
- F `ValidatorAgent`: 공개 게이트 검증 (`published` vs `review_required`)
- G `PersisterAgent`: DB 적재/버전 증가/배치 연동

## 실행 방법

### 1) 배치 실행 (CLI)
```bash
$env:PYTHONPATH='src'
python -m tax_exam_app --mode collect_and_process --db-path ./tax_exam.db --years 2024-2025 --subjects TAX_LAW_1,TAX_LAW_2
```

### 1-1) 2025 문제/정답 DB화 전용
```bash
$env:PYTHONPATH='src'
python -m tax_exam_app.ingest_2025 --db-path ./tax_exam.db
```
- `data/qnet/2025`의 문제 PDF/최종정답 자료를 읽어 `exam_questions_2025` 테이블에 적재합니다.
- `review_flag=1`은 2026-02 기준 세법/IFRS 민감 문항으로 자동 검수 플래그가 설정된 항목입니다.

### 1-2) 문제은행 추출 + 해설 일괄 업데이트
```bash
$env:PYTHONPATH='src'
python -m tax_exam_app.build_question_bank --db-path ./tax_exam.db --year 2025
```
- `exam_question_bank` 테이블에 문제를 업서트합니다.
- 2025의 경우 `exam_answers_2025`와 동기화하여 정답을 연결합니다.
- `StudentExplanationRefreshAgent`가 수험생용 해설을 전 문항 재생성합니다.

### 1-3) 최근 3개년(2023~2025) 일괄 처리
```bash
$env:PYTHONPATH='src'
python -m tax_exam_app.process_recent_years --db-path ./tax_exam.db --years 2023-2025
```
- 문제 추출/적재, 현행 기준 검수 플래그, 해설 갱신을 한 번에 실행합니다.
- 2교시 회계학개론 중복은 자동 제거됩니다.
- 현재 2023/2024 최종정답 HWP는 이미지형이라 자동 텍스트 추출이 제한되어 해당 문항은 검수 플래그로 관리합니다.

### 1-4) 문제은행 컨텐츠 고도화(LLM 해설 + OX 보기 판정)
```bash
$env:PYTHONPATH='src'
python -m tax_exam_app.enrich_bank_content --db-path ./tax_exam.db --years 2025 --model gpt-4.1-mini
```
- `exam_question_bank.explanation_text`를 수험생 친화형 상세 해설로 갱신하고, `exam_explanation_history`에 이력을 저장합니다.
- `exam_choice_ox_bank`에 각 보기의 OX 문제 전환 가능 여부(`is_ox_eligible`)와 예상 정답(`expected_ox`)을 저장합니다.
- `OPENAI_API_KEY`가 있으면 OpenAI Responses API를 사용하고, 없으면 템플릿 해설로 안전하게 대체합니다.

### 2) 웹 화면 실행 (배포 대상 화면)
```bash
python -m tax_exam_app.build_service_db --source-db tax_exam.db --target-db tax_exam_service.db
```

### 2-1) 웹 서버 실행
```bash
python -m uvicorn tax_exam_app.web:app --app-dir src --host 127.0.0.1 --port 8000
```
브라우저에서 `http://127.0.0.1:8000` 접속

### 2-2) 사용자 데이터 초기화
```bash
pip install -e .
python -m tax_exam_app.reset_user_data --db-path tax_exam_service.db
```
- 풀이기록/점수/즐겨찾기/오답노트/보기가리기 설정을 초기화합니다.

### 2-3) 웹앱 배포 가이드(비개발자용)
- `docs/DEPLOY_WEBAPP_NONDEV.md` 참고

## 주요 API (서비스 배포)
- `POST /api/batch/run` 배치 실행
- `GET /api/questions` 문제 목록
- `GET /api/questions/{id}` 문제 상세
- `POST /api/notes` 오답노트 저장
- `GET /api/notes` 오답노트 조회
- `GET /api/stats` 대시보드 통계
- `GET /api/mock/options` 모의고사 가능 과목 목록
- `GET /api/mock/questions` 모의고사 문제(정답 비공개)
- `POST /api/mock/submit` 채점/오답/해설 반환
- `GET /api/ox/questions` OX 모드용 보기 지문(판정 완료본) 조회

참고: 서비스 배포에서는 배치/관리 API(`batch`, `questions`, `notes`)는 `503`으로 비활성화됩니다.

## 현재 상태
- E2E 동작 확인 완료: 배치 -> 문제 공개 -> 화면 조회 -> 오답노트 저장
- 크롤링/LLM은 스텁 기반으로 동작하며, 실제 배포 전 외부 연동이 필요함

