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
COL_EXPLANATION = "해설"
COL_ANSWERED = "답변여부"

ENTRY_RE = re.compile(r"(?m)^\s*(?:\*\*)?(\d{1,2})\.\s*")
ANSWER_RE = re.compile(r"정답\s*:\s*([①②③④⑤1-5])")
CITE_START_RE = re.compile(r"\[cite_start\]")
CITE_REF_RE = re.compile(r"\[cite:\s*[\d,\s]+\]")

CIRCLE_TO_DIGIT = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}


def normalize_answer(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in CIRCLE_TO_DIGIT:
        return CIRCLE_TO_DIGIT[text]
    ordered: list[str] = []
    for ch in text:
        if ch in "12345" and ch not in ordered:
            ordered.append(ch)
    return ",".join(ordered)


def clean_explanation(text: str) -> str:
    cleaned = CITE_START_RE.sub("", text)
    cleaned = CITE_REF_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_solution_text(path: Path) -> dict[int, tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    matches = list(ENTRY_RE.finditer(text))
    parsed: dict[int, tuple[str, str]] = {}
    for index, match in enumerate(matches):
        qno = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        answer_match = ANSWER_RE.search(block)
        if not answer_match:
            continue
        answer = normalize_answer(answer_match.group(1))
        explanation = clean_explanation(block)
        parsed[qno] = (answer, explanation)
    return parsed


def import_solution_text(*, db_path: Path, year: int, subject: str, text_path: Path) -> dict[str, int]:
    records = parse_solution_text(text_path)
    if not records:
        raise ValueError(f"No parsable solution records found: {text_path}")

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_QUESTIONS}")')}
        if COL_ANSWERED not in columns:
            conn.execute(
                f'ALTER TABLE "{TABLE_QUESTIONS}" ADD COLUMN "{COL_ANSWERED}" INTEGER NOT NULL DEFAULT 0'
            )
            conn.commit()

        sql = f"""
            UPDATE "{TABLE_QUESTIONS}"
            SET "{COL_ANSWER}" = ?, "{COL_EXPLANATION}" = ?, "{COL_ANSWERED}" = 1
            WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ? AND "{COL_QNO}" = ?
        """

        updated = 0
        for qno, (answer, explanation) in sorted(records.items()):
            cursor = conn.execute(sql, (answer, explanation, int(year), subject.strip(), int(qno)))
            if cursor.rowcount and cursor.rowcount > 0:
                updated += int(cursor.rowcount)
        conn.commit()

        mismatch = 0
        matched = 0
        no_distributed = 0
        grade_sql = f"""
            SELECT "{COL_ANSWER}", "{COL_DISTRIBUTED}"
            FROM "{TABLE_QUESTIONS}"
            WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?
            ORDER BY "{COL_QNO}"
        """
        for answer, distributed in conn.execute(grade_sql, (int(year), subject.strip())).fetchall():
            n_answer = normalize_answer(answer)
            n_distributed = normalize_answer(distributed)
            if not n_distributed:
                no_distributed += 1
            elif n_answer == n_distributed:
                matched += 1
            else:
                mismatch += 1
        return {
            "parsed": len(records),
            "updated": updated,
            "matched": matched,
            "mismatch": mismatch,
            "no_distributed": no_distributed,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import subject solution text into DB and grade against 답_배포.")
    parser.add_argument("--db-path", default="data/questions.db")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--file", default="")
    parser.add_argument("--data-root", default="data")
    args = parser.parse_args()

    if args.file:
        text_path = Path(args.file)
    else:
        year_dir = Path(args.data_root) / str(args.year)
        text_path = find_year_file(year_dir, f"{args.subject}풀이.txt", kind="solution")

    result = import_solution_text(
        db_path=Path(args.db_path),
        year=int(args.year),
        subject=str(args.subject),
        text_path=text_path,
    )
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
