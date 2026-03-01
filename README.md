# tax_exam3

세무사 1차 시험 대비용 로컬/웹 학습 도구입니다.

이 프로젝트는 다음 기능을 하나의 SQLite DB(`data/questions.db`) 기준으로 묶어 운용합니다.

- 모의고사 모드
- OX 모드
- OX 낙하 게임
- 오답관리
- 공지사항
- 묻고 답하기(현재는 시범 단계)

## 핵심 구조

- [config/README.md](/e:/Project/tax_exam3/config/README.md)
  - 로컬 설정 파일 위치와 보안 주의사항
- [data/README.md](/e:/Project/tax_exam3/data/README.md)
  - 원본 문제, 풀이, OX 텍스트, SQLite DB 저장 구조
- [scripts/README.md](/e:/Project/tax_exam3/scripts/README.md)
  - 데이터 적재/동기화/검증 스크립트
- [webapp/README.md](/e:/Project/tax_exam3/webapp/README.md)
  - 웹 화면, API, 서버 실행 구조
- [docs/README.md](/e:/Project/tax_exam3/docs/README.md)
  - 아키텍처와 로드맵 문서
- [.logs/README.md](/e:/Project/tax_exam3/.logs/README.md)
  - 로컬 서버 로그 용도

## 현재 권장 데이터 구축 순서

1. PDF 문제 적재
   - `python scripts/load_pdf_questions.py --data-root data --years 2021 2022 2023 2024 2025`
2. 과목별 풀이 적재
   - `python scripts/import_solution_text.py --db-path data/questions.db --year 2025 --subject 재정학`
3. 실제 배포답안 동기화
   - `python scripts/sync_distributed_answers.py --db-path data/questions.db --data-root data --years 2023 2024 2025`
4. OX 텍스트 적재
   - `python scripts/import_ox_text.py --db-path data/questions.db --year 2025 --subject 재정학 --data-root data`
5. 로컬 웹서버 실행
   - `python webapp/server.py`

## 실행

```powershell
python webapp/server.py --host 127.0.0.1 --port 8000
```

- 기본 접속 주소: `http://127.0.0.1:8000`
- DB 경로: `data/questions.db`

## 배포

- 배포 설정 파일: [render.yaml](/e:/Project/tax_exam3/render.yaml)
- 컨테이너 정의: [Dockerfile](/e:/Project/tax_exam3/Dockerfile)
- `main` 브랜치 푸시 시 Render 자동배포를 전제로 운용 중입니다.

## 앞으로 해야 할 일

- 로그인 기능
  - 현재는 기기 기반/게스트 기반 상태 저장 비중이 큼
  - 사용자 계정 단위 동기화가 필요함
- 두문자관리
  - 과목/문제별 두문자 저장, 검색, 복습 흐름이 아직 없음
- 게시판 기능 고도화
  - 현재 묻고 답하기는 시범 단계
  - 실제 운영형 질문/답변, 관리 기능, 신고/숨김 기능 보강 필요
- 데이터 품질 검수
  - 과거 연도 미완성 데이터
  - 법 개정 반영 검증
  - OX 진술 정확도 재검토

## 운영 메모

- 2025 데이터가 현재 기준 메인 운영 대상입니다.
- 2024~2022 데이터는 일부 존재하지만 완성도/검수 상태가 균일하지 않습니다.
- 외부 LLM 연동 스크립트는 보조 도구이며, 배포 서비스의 필수 런타임은 아닙니다.
