# 세무사 돌돌이 배포 가이드 (비개발자용)

이 문서는 비개발자 기준으로, 현재 프로젝트를 웹앱 형태로 배포하는 최소 절차를 정리한 문서입니다.

## 1) 현재 준비된 상태

- 앱 이름은 `세무사 돌돌이`로 반영되어 있습니다.
- Docker 배포 파일이 준비되어 있습니다.
  - `Dockerfile`
  - `Procfile`
  - `.env.example`
- 사용자 학습 데이터(풀이 기록/즐겨찾기/메모/가리기 설정) 초기화 스크립트가 준비되어 있습니다.
  - `python -m tax_exam_app.reset_user_data`

## 2) 배포 전에 반드시 할 일

1. 기존에 노출된 OpenAI API 키가 있다면 폐기(재발급)합니다.
2. 새 API 키를 준비합니다.
3. 테스트용 사용자 데이터 초기화 후 배포합니다.

## 3) 로컬 실행 확인 (배포 전 점검)

```bash
pip install -e .
python -m uvicorn tax_exam_app.web:app --app-dir src --host 127.0.0.1 --port 8000
```

- 접속: `http://127.0.0.1:8000`
- 헬스체크: `http://127.0.0.1:8000/api/health`

## 4) 사용자 데이터 초기화 방법

### 전체 사용자 데이터 초기화

```bash
pip install -e .
python -m tax_exam_app.reset_user_data --db-path tax_exam.db
```

### 특정 사용자만 초기화

```bash
pip install -e .
python -m tax_exam_app.reset_user_data --db-path tax_exam.db --user-id user_123
```

## 5) Render로 배포 (가장 쉬운 방법)

준비물
- GitHub 계정
- Render 계정
- OpenAI API 키

절차
1. 현재 프로젝트를 GitHub 저장소에 업로드합니다.
2. Render에서 `New > Web Service`를 선택합니다.
3. GitHub 저장소를 연결합니다.
4. Runtime은 `Docker`를 선택합니다.
5. 환경변수를 입력합니다.
   - `OPENAI_API_KEY`: 발급받은 키
   - `OPENAI_API_URL`: `https://api.openai.com/v1/responses`
   - `OPENAI_CHAT_API_URL`: `https://api.openai.com/v1/chat/completions`
   - `PORT`: `8000`
6. `Create Web Service`를 눌러 배포합니다.

## 6) 운영 체크리스트

- API 키는 코드에 넣지 않고 환경변수로만 관리
- 배포 직전 사용자 데이터 초기화 실행
- DB 파일(`tax_exam.db`) 주기적 백업
- 기능 점검
  - 모의고사 문제 풀이/채점
  - OX 문제 정답/오답 하이라이트
  - 즐겨찾기/메모 저장 및 조회
  - 뒤로가기/홈 이동 동작
