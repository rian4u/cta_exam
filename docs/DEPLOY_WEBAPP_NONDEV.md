# 세무사 돌돌이 배포 가이드 (비개발자용)

이 문서는 비개발자 기준으로 웹앱 배포 절차를 가장 짧게 정리한 문서입니다.

## 1) 배포 전 핵심 개념
- 개발 DB: `tax_exam.db` (수집/가공/검수 작업용)
- 배포 DB: `tax_exam_service.db` (서비스 조회/사용자 풀이용)
- 배포에는 `tax_exam_service.db`만 사용합니다.

## 2) 배포용 DB 만들기
```bash
pip install -e .
python -m tax_exam_app.build_service_db --source-db tax_exam.db --target-db tax_exam_service.db
```

## 3) 로컬 최종 확인
```bash
python -m uvicorn tax_exam_app.web:app --app-dir src --host 127.0.0.1 --port 8000
```
- 접속: `http://127.0.0.1:8000`
- 헬스체크: `http://127.0.0.1:8000/api/health`

## 4) 사용자 데이터 초기화
### 전체 초기화
```bash
python -m tax_exam_app.reset_user_data --db-path tax_exam_service.db
```

### 특정 사용자만 초기화
```bash
python -m tax_exam_app.reset_user_data --db-path tax_exam_service.db --user-id user_123
```

## 5) Render 배포 절차
1. GitHub 저장소 최신화
2. Render에서 `New > Web Service`
3. 저장소 연결 후 Runtime을 `Docker`로 선택
4. `Create Web Service` 실행

## 6) 배포 후 점검
- `https://<서비스URL>/api/health` 가 `{"ok":true}` 인지 확인
- 메인 화면/모의고사/OX/즐겨찾기 동작 확인
- 배치 API(`/api/batch/*`)는 서비스 배포에서 비활성화(503) 상태가 정상
