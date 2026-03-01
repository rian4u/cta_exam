# Architecture

## 1. 시스템 개요

이 프로젝트는 프레임워크 의존을 최소화한 구조입니다.

- 프런트엔드: 정적 HTML/CSS/JS
- 서버: [webapp/server.py](/e:/Project/tax_exam3/webapp/server.py)
  - `http.server` 기반의 단순 API/정적 파일 서버
- 저장소: SQLite([data/questions.db](/e:/Project/tax_exam3/data/questions.db))

즉, 배포와 로컬 실행 모두 같은 DB 중심 구조를 공유합니다.

## 2. 데이터 흐름

1. 원본 파일 입력
   - `data/{연도}`의 PDF/HWP/TXT
   - `data/OX문제`의 OX 텍스트
2. 스크립트 적재
   - `scripts/*.py`가 원본을 파싱해 SQLite에 반영
3. 서버 제공
   - `webapp/server.py`가 DB를 읽어 JSON API 응답
4. 화면 렌더링
   - `webapp/*.html`, `webapp/*.js`가 API를 호출해 화면 구성

## 3. 주요 DB 개념

실제 테이블명은 일부 한글/기존 명명 흔적이 있으나, 역할은 아래와 같습니다.

- 문제
  - 객관식 문제 본문, 보기, 정답, 해설, 배포답안
- OX
  - OX 지문, O/X 정답, 해설
- 오답노트
  - 사용자별 신호등/코멘트
- 공지
  - 관리자 공지사항
- qa_posts / qa_answers
  - 묻고 답하기 시범 데이터

## 4. 프런트엔드 화면 구성

- [index.html](/e:/Project/tax_exam3/webapp/index.html)
  - 메인 진입
- [mock-exam.html](/e:/Project/tax_exam3/webapp/mock-exam.html)
  - 모의고사
- [ox-mode.html](/e:/Project/tax_exam3/webapp/ox-mode.html)
  - OX 학습
- [game.html](/e:/Project/tax_exam3/webapp/game.html)
  - OX 낙하 게임
- [wrong-note.html](/e:/Project/tax_exam3/webapp/wrong-note.html)
  - 오답관리
- [notice.html](/e:/Project/tax_exam3/webapp/notice.html)
  - 공지
- [qa.html](/e:/Project/tax_exam3/webapp/qa.html)
  - 묻고 답하기
- [contact.html](/e:/Project/tax_exam3/webapp/contact.html)
  - 문의 안내

## 5. 유지보수 시 주의점

- 과목 목록은 프런트와 서버 양쪽에서 맞춰야 함
  - 예: `mock-exam.js`, `server.py`
- OX 데이터는 파일 수정 후 재적재해야 실제 서비스에 반영됨
- 일부 구형 스크립트는 예전 테이블명/경로 호환 코드를 포함함
- 소스 일부에는 인코딩 흔적이 남아 있으므로, 기능 수정 전 실제 동작 기준으로 검증 필요
