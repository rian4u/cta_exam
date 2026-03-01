# data

프로젝트의 실데이터와 SQLite DB를 보관하는 폴더입니다.

## 핵심 파일

- [questions.db](/e:/Project/tax_exam3/data/questions.db)
  - 웹앱이 직접 읽는 SQLite DB
  - 문제, OX, 오답관리, 공지, QA 데이터가 함께 저장됨

## 하위 폴더

- [2021](/e:/Project/tax_exam3/data/2021)
- [2022](/e:/Project/tax_exam3/data/2022)
- [2023](/e:/Project/tax_exam3/data/2023)
- [2024](/e:/Project/tax_exam3/data/2024)
- [2025](/e:/Project/tax_exam3/data/2025)
  - 연도별 원본 문제, 정답, 풀이 보관
- [OX문제](/e:/Project/tax_exam3/data/OX문제)
  - 공용 OX 텍스트 원본
- [review](/e:/Project/tax_exam3/data/review)
  - 불일치 검증용 중간 산출물

## 데이터 구축 원칙

1. 원본 PDF/HWP/TXT는 가능하면 그대로 보관
2. 스크립트는 이 폴더를 읽어 `questions.db`를 갱신
3. 웹앱은 원본 텍스트가 아니라 `questions.db`를 조회

## 상태 메모

- 현재 실사용 기준은 2025 데이터 중심
- 과거 연도는 연도별 완성도 차이가 있음
- OX 텍스트는 연도 폴더가 아니라 공용 [OX문제](/e:/Project/tax_exam3/data/OX문제) 폴더를 우선 사용
