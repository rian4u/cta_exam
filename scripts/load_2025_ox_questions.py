from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

TABLE_OX = "문제_OX"
COL_YEAR = "출제연도"
COL_SUBJECT = "과목"
COL_QNO = "문제번호"
COL_QUESTION = "문제"
COL_ANSWER = "답"
COL_EXPLANATION = "해설"

QUESTION_LINE_RE = re.compile(r"^\*\s*\*\*\[Q\]\*\*\s*(.+?)\s*$")
ANSWER_LINE_RE = re.compile(r"^\*\s*\*\*[^*]+:\*\*\s*([OX])\s*$")
LABEL_LINE_RE = re.compile(r"^\*?\s*\*\*[^*]+:\*\*\s*(.*)$")
QUESTION_PREFIX_RE = re.compile(r"^\s*(?:문제\s*)?(?:\d+|[①-⑳])\s*[\.\)\]:：\-]\s*")


def normalize_ox_question_text(text: str) -> str:
    normalized = (text or "").strip()
    return QUESTION_PREFIX_RE.sub("", normalized).strip()


def ensure_ox_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_OX}" (
            ox문제id INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_QNO}" INTEGER NOT NULL,
            "{COL_QUESTION}" TEXT NOT NULL,
            "{COL_ANSWER}" TEXT NOT NULL,
            "{COL_EXPLANATION}" TEXT NOT NULL,
            UNIQUE ("{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
        )
        """
    )
    conn.commit()


def parse_ox_entries(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict] = []

    index = 0
    while index < len(lines):
        question_match = QUESTION_LINE_RE.match(lines[index].strip())
        if not question_match:
            index += 1
            continue

        question_text = normalize_ox_question_text(question_match.group(1))
        answer = ""
        explanation_lines: list[str] = []
        in_explanation = False
        index += 1

        while index < len(lines):
            line = lines[index].strip()
            if QUESTION_LINE_RE.match(line):
                break

            answer_match = ANSWER_LINE_RE.match(line)
            if answer_match:
                answer = answer_match.group(1)
                index += 1
                continue

            label_match = LABEL_LINE_RE.match(line)
            if label_match and "[Q]" not in line and not answer_match:
                in_explanation = True
                tail = label_match.group(1).strip()
                if tail:
                    explanation_lines.append(tail)
                index += 1
                continue

            if in_explanation:
                if line and line != "*":
                    explanation_lines.append(line.lstrip("* ").strip())
            index += 1

        explanation = "\n".join(explanation_lines).strip()
        if question_text and answer and explanation:
            entries.append(
                {
                    "question": question_text,
                    "answer": answer,
                    "explanation": explanation,
                }
            )

    return entries


def load_ox_questions(*, data_file: Path, db_path: Path, year: int, subject: str) -> int:
    entries = parse_ox_entries(data_file)
    if not entries:
        raise ValueError("OX 데이터 파싱 결과가 비어 있습니다.")

    conn = sqlite3.connect(db_path)
    try:
        ensure_ox_table(conn)
        conn.execute(
            f'DELETE FROM "{TABLE_OX}" WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?',
            (year, subject),
        )
        insert_sql = f"""
            INSERT INTO "{TABLE_OX}"
            ("{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_QUESTION}", "{COL_ANSWER}", "{COL_EXPLANATION}")
            VALUES (?, ?, ?, ?, ?, ?)
        """
        conn.executemany(
            insert_sql,
            [
                (year, subject, number, entry["question"], entry["answer"], entry["explanation"])
                for number, entry in enumerate(entries, start=1)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load 2025 OX questions into SQLite DB")
    parser.add_argument("--data-file", default="data/2025/재정학ox.txt")
    parser.add_argument("--db-path", default="data/questions.db")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--subject", default="재정학")
    args = parser.parse_args()

    count = load_ox_questions(
        data_file=Path(args.data_file),
        db_path=Path(args.db_path),
        year=args.year,
        subject=args.subject,
    )
    print(f"OX 적재 완료: {args.db_path} ({args.subject} {args.year})")
    print(f"총 적재 문항 수: {count}")


if __name__ == "__main__":
    main()
