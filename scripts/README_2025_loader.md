# 2025 문제 적재 메모

## 기본 실행

```powershell
python scripts/load_2025_questions.py --data-dir data/2025 --db-path data/questions.db --year 2025
```

## 이 스크립트가 읽는 데이터

- 1교시 PDF
- 2교시 PDF(상법/민법/행정소송법 선택형 포함)
- 과목별 풀이 TXT
- [실제정답.txt](/e:/Project/tax_exam3/data/2025/실제정답.txt)

## 현재 위치 규칙

- 문제 PDF
  - `data/2025/원본문제`
  - 또는 `data/2025`
- 풀이 TXT
  - `data/2025/풀이`
  - 또는 `data/2025`
- OX 텍스트
  - 현재는 공용 `data/OX문제` 우선

## 출력 결과

적재 결과는 최종적으로 [questions.db](/e:/Project/tax_exam3/data/questions.db)에 반영됩니다.

주요 반영 컬럼:

- 문제 본문
- 보기 1~5
- 정답
- 해설
- 답_배포
- HTML 렌더 보조 데이터

## 주의

- 이 스크립트는 2025 데이터 포맷에 맞춘 로직이 많습니다.
- 여러 연도를 공통 처리할 때는 [load_pdf_questions.py](/e:/Project/tax_exam3/scripts/load_pdf_questions.py)를 우선 검토하는 편이 맞습니다.
