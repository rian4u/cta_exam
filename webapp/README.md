# webapp

정적 화면과 로컬 API 서버를 함께 두는 폴더입니다.

## 서버

- [server.py](/e:/Project/tax_exam3/webapp/server.py)
  - `http.server` 기반
  - 정적 파일 서빙 + JSON API 제공
  - SQLite([data/questions.db](/e:/Project/tax_exam3/data/questions.db)) 직접 조회

실행:

```powershell
python webapp/server.py --host 127.0.0.1 --port 8000
```

## 화면 파일

- [index.html](/e:/Project/tax_exam3/webapp/index.html)
  - 메인 화면
- [mock-exam.html](/e:/Project/tax_exam3/webapp/mock-exam.html)
  - 모의고사
- [ox-mode.html](/e:/Project/tax_exam3/webapp/ox-mode.html)
  - OX 문제 풀이
- [game.html](/e:/Project/tax_exam3/webapp/game.html)
  - OX 낙하 게임
- [wrong-note.html](/e:/Project/tax_exam3/webapp/wrong-note.html)
  - 오답관리
- [notice.html](/e:/Project/tax_exam3/webapp/notice.html)
  - 공지사항
- [qa.html](/e:/Project/tax_exam3/webapp/qa.html)
  - 묻고 답하기(시범)
- [contact.html](/e:/Project/tax_exam3/webapp/contact.html)
  - 문의 안내

## 스크립트 파일

- [mock-exam.js](/e:/Project/tax_exam3/webapp/mock-exam.js)
  - 모의고사 UI 상태 관리, 문제/해설 렌더링
- [ox-mode.js](/e:/Project/tax_exam3/webapp/ox-mode.js)
  - OX 필터, 해설, 복습, 신호등 저장
- [game.js](/e:/Project/tax_exam3/webapp/game.js)
  - OX 낙하 게임 로직, 복습 패널, 신호등 저장
- [wrong-note.js](/e:/Project/tax_exam3/webapp/wrong-note.js)
  - 오답관리 조회/필터/인라인 해설
- [notice.js](/e:/Project/tax_exam3/webapp/notice.js)
  - 공지 목록 렌더링
- [qa.js](/e:/Project/tax_exam3/webapp/qa.js)
  - 질문/답변 UI
- [contact.js](/e:/Project/tax_exam3/webapp/contact.js)
  - 문의 이메일 노출
- [skin.js](/e:/Project/tax_exam3/webapp/skin.js)
  - 공통 UI 보조

## 스타일

- [styles.css](/e:/Project/tax_exam3/webapp/styles.css)
  - 전체 공통 스타일
- [game.css](/e:/Project/tax_exam3/webapp/game.css)
  - 게임 화면 전용, 특히 모바일 레이아웃 보정

## 운영 메모

- 현재는 프런트/서버가 한 폴더에 있어 배포 단순성은 높지만 결합도도 높습니다.
- 과목 목록, 연도 정책, 오답관리 저장 규칙은 프런트와 서버를 같이 맞춰야 합니다.
