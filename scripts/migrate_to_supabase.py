"""
SQLite questions.db → Supabase PostgreSQL 마이그레이션 스크립트

사용법:
  1. 아래 환경변수를 설정하거나 .env 파일에 저장
     SUPABASE_URL=https://zlxinobibdsplirysgqy.supabase.co
     SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...

  2. pip install requests python-dotenv
  3. python scripts/migrate_to_supabase.py

  먼저 Supabase에서 supabase/schema.sql 을 실행해야 합니다.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webapp"))

try:
    import requests
except ImportError:
    print("requests 패키지가 필요합니다: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# ── 환경변수 ─────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY 환경변수를 설정해주세요.")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

BATCH_SIZE = 50  # Supabase REST API 한 번에 삽입할 행 수
RETRY_DELAY = 2  # 실패 시 재시도 대기 (초)


def supabase_upsert(table: str, rows: list[dict], *, on_conflict: str) -> bool:
    """Supabase REST API로 배치 upsert. 실패 시 True 반환."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"
    headers = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"}
    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=rows, timeout=30)
            if resp.ok:
                return True
            print(f"  [WARN] {table} upsert 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
            if attempt < 2:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"  [ERROR] 네트워크 오류: {e}")
            if attempt < 2:
                time.sleep(RETRY_DELAY)
    return False


def batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def migrate_questions() -> None:
    print("\n=== 기출문제 마이그레이션 ===")
    try:
        from server import SUBJECTS, fetch_questions
    except ImportError as e:
        print(f"  [ERROR] server.py import 실패: {e}")
        return

    years = [2025, 2024, 2023, 2022]
    total = 0
    for year in years:
        for subject in SUBJECTS:
            questions = fetch_questions(year, subject)
            if not questions:
                continue
            rows = [
                {
                    "year": year,
                    "subject": subject,
                    "original_no": q["original_no"],
                    "stem": q["stem"],
                    "stem_html": q["stem_html"],
                    "options": json.dumps(q["options"], ensure_ascii=False),
                    "options_html": json.dumps(q["options_html"], ensure_ascii=False),
                    "answer": q["answer"],
                    "distributed_answer": q["distributed_answer"],
                    "explanation": q["explanation"],
                }
                for q in questions
            ]
            ok = False
            for batch in batched(rows, BATCH_SIZE):
                ok = supabase_upsert("questions", batch, on_conflict="year,subject,original_no")
            total += len(rows)
            status = "✓" if ok else "✗"
            print(f"  {status} {year} {subject}: {len(questions)}문제")
    print(f"  총 {total}행 처리 완료")


def migrate_ox_questions() -> None:
    print("\n=== OX 문제 마이그레이션 ===")
    try:
        from server import SUBJECTS, fetch_ox_questions
    except ImportError as e:
        print(f"  [ERROR] server.py import 실패: {e}")
        return

    years = [2025, 2024, 2023, 2022]
    total = 0
    for year in years:
        for subject in SUBJECTS:
            questions = fetch_ox_questions(year, subject)
            if not questions:
                continue
            rows = [
                {
                    "year": year,
                    "subject": subject,
                    "original_no": q["original_no"],
                    "source_no": q.get("source_no", q["original_no"]),
                    "stable_id": q.get("stable_id", ""),
                    "question": q["question"],
                    "answer": q["answer"],
                    "explanation": q["explanation"],
                }
                for q in questions
            ]
            ok = False
            for batch in batched(rows, BATCH_SIZE):
                ok = supabase_upsert("ox_questions", batch, on_conflict="year,subject,original_no")
            total += len(rows)
            status = "✓" if ok else "✗"
            print(f"  {status} {year} {subject}: {len(questions)}문제")
    print(f"  총 {total}행 처리 완료")


def migrate_notices() -> None:
    print("\n=== 공지게시판 마이그레이션 ===")
    try:
        from server import fetch_notices
    except ImportError as e:
        print(f"  [ERROR] server.py import 실패: {e}")
        return

    notices = fetch_notices(include_unpublished=True)
    if not notices:
        print("  공지 없음 (건너뜀)")
        return

    rows = [
        {
            "title": n["title"],
            "body": n["body"],
            "author": n["author"],
            "is_published": bool(n["is_published"]),
            "created_at": n["created_at"] or None,
            "updated_at": n["updated_at"] or None,
        }
        for n in notices
    ]

    # 공지는 id가 다를 수 있으므로 INSERT만 (중복 방지를 위해 기존 테이블 비우기 옵션)
    url = f"{SUPABASE_URL}/rest/v1/notices"
    hdrs = {**HEADERS, "Prefer": "return=minimal"}
    resp = requests.post(url, headers=hdrs, json=rows, timeout=30)
    if resp.ok:
        print(f"  ✓ {len(rows)}건 삽입 완료")
    else:
        print(f"  ✗ 실패: {resp.text[:300]}")


def main() -> None:
    print("=== Supabase 마이그레이션 시작 ===")
    print(f"  대상: {SUPABASE_URL}")
    print()
    print("  주의: Supabase에서 supabase/schema.sql 을 먼저 실행했는지 확인하세요.")
    print()

    migrate_questions()
    migrate_ox_questions()
    migrate_notices()

    print("\n=== 완료 ===")
    print("  Supabase Dashboard > Table Editor 에서 데이터를 확인하세요.")


if __name__ == "__main__":
    main()
