from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from data_paths import find_year_file


TABLE_QUESTIONS = "문제"
COL_YEAR = "출제연도"
COL_SUBJECT = "과목"
COL_QNO = "문제번호"
COL_ANSWER = "답"
COL_DISTRIBUTED = "답_배포"

SUBJECTS = {
    "재정학",
    "세법학개론",
    "회계학개론",
    "상법",
    "민법",
    "행정소송법",
}

PAIR_RE = re.compile(r"\*\*(\d{1,2})\*\*:(.*?)(?=,\s*\*\*\d{1,2}\*\*:|$)")


def normalize_answer(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "모두" in text:
        return "1,2,3,4,5"

    ordered: list[str] = []
    for ch in text:
        if ch in "12345" and ch not in ordered:
            ordered.append(ch)
    return ",".join(ordered)


def parse_published_answers(path: Path) -> dict[tuple[str, int], str]:
    text = path.read_text(encoding="utf-8")
    mapping: dict[tuple[str, int], str] = {}
    current_subject = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalized = line.replace("*", "").strip()
        if normalized in SUBJECTS:
            current_subject = normalized
            continue

        if not current_subject:
            continue

        for match in PAIR_RE.finditer(line):
            qno = int(match.group(1))
            answer = normalize_answer(match.group(2))
            if answer:
                mapping[(current_subject, qno)] = answer

    return mapping


def update_from_mapping(
    conn: sqlite3.Connection,
    *,
    year: int,
    mapping: dict[tuple[str, int], str],
) -> int:
    if not mapping:
        return 0

    sql = f"""
        UPDATE "{TABLE_QUESTIONS}"
        SET "{COL_DISTRIBUTED}" = ?
        WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ? AND "{COL_QNO}" = ?
    """
    updated = 0
    for (subject, qno), answer in mapping.items():
        cur = conn.execute(sql, (answer, year, subject, qno))
        if cur.rowcount and cur.rowcount > 0:
            updated += int(cur.rowcount)
    return updated


def fallback_copy_from_answer(conn: sqlite3.Connection, *, year: int) -> int:
    sql = f"""
        UPDATE "{TABLE_QUESTIONS}"
        SET "{COL_DISTRIBUTED}" = "{COL_ANSWER}"
        WHERE "{COL_YEAR}" = ?
          AND COALESCE(TRIM("{COL_ANSWER}"), '') <> ''
    """
    cur = conn.execute(sql, (year,))
    return int(cur.rowcount or 0)


def count_filled(conn: sqlite3.Connection, *, year: int) -> tuple[int, int]:
    sql = f"""
        SELECT COUNT(*),
               SUM(CASE WHEN COALESCE(TRIM("{COL_DISTRIBUTED}"), '') <> '' THEN 1 ELSE 0 END)
        FROM "{TABLE_QUESTIONS}"
        WHERE "{COL_YEAR}" = ?
    """
    total, filled = conn.execute(sql, (year,)).fetchone()
    return int(total or 0), int(filled or 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync 문제.답_배포 from 실제정답.txt (fallback: 답)."
    )
    parser.add_argument("--db-path", default="data/questions.db")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025])
    args = parser.parse_args()

    db_path = Path(args.db_path)
    data_root = Path(args.data_root)

    conn = sqlite3.connect(db_path)
    try:
        for year in args.years:
            try:
                txt_path = find_year_file(data_root / str(year), "실제정답.txt", kind="problem")
                mapping = parse_published_answers(txt_path)
                updated = update_from_mapping(conn, year=year, mapping=mapping)
                source = str(txt_path)
            except FileNotFoundError:
                updated = fallback_copy_from_answer(conn, year=year)
                source = "fallback: 문제.답"

            total, filled = count_filled(conn, year=year)
            print(f"[{year}] source={source}")
            print(f"  updated={updated}, filled={filled}/{total}")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
