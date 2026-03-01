from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import unicodedata
from pathlib import Path

from data_paths import find_year_file

TABLE_OX = "OX"

COL_YEAR = "\ucd9c\uc81c\uc5f0\ub3c4"
COL_SUBJECT = "\uacfc\ubaa9"
COL_QNO = "\ubb38\uc81c\ubc88\ud638"
COL_SOURCE_QNO = "\uc6d0\ubb38\ubc88\ud638"
COL_STABLE_ID = "stable_id"
COL_QUESTION = "\ubb38\uc81c"
COL_ANSWER = "\ub2f5"
COL_EXPLANATION = "\ud574\uc124"

ANSWER_LABEL_RE = r"(?:\uC815\uB2F5|\uB2F5)"
EXPLANATION_LABEL_RE = r"(?:\uC124\uBA85|\uD574\uC124)"

ENTRY_RE = re.compile(r"(?m)^\s*(?:\*+\s*)?(\d{1,3})\.\s*")
ANSWER_RE = re.compile(rf"{ANSWER_LABEL_RE}\s*[:\uff1a]?\s*([OoXx])")
INLINE_ANSWER_RE = re.compile(rf"\(\s*{ANSWER_LABEL_RE}\s*[:\uff1a]?\s*([OoXx])\s*\)")
EXPLANATION_RE = re.compile(rf"{EXPLANATION_LABEL_RE}\s*[:\uff1a]?\s*(.+)")
SEGMENT_SPLIT_RE = re.compile(r"\s+/\s+")
TRAILING_STARS_RE = re.compile(r"\*+\s*$")


def clean_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\[cite_start\]", "", text)
    text = re.sub(r"\[cite:\s*[\d,\s]+\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_ox_answer(value: str) -> str:
    token = str(value or "").strip().upper()
    return token if token in {"O", "X"} else ""


def canonicalize_question(value: str) -> str:
    text = unicodedata.normalize("NFKC", clean_text(value)).casefold()
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def build_stable_id(source_qno: int, question: str, occurrence: int = 1) -> str:
    canonical = canonicalize_question(question)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    base = f"ox-{int(source_qno)}-{digest}"
    if occurrence <= 1:
        return base
    return f"{base}-{occurrence}"


def strip_header_prefix(line: str, qno: int) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^\*+", "", text).strip()
    text = re.sub(rf"^{qno}\.\s*", "", text)
    text = INLINE_ANSWER_RE.sub("", text).strip()
    text = TRAILING_STARS_RE.sub("", text).strip()
    return text


def parse_inline_segments(text: str) -> tuple[str, str, str]:
    normalized = clean_text(text)
    if not normalized:
        return "", "", ""

    parts = [part.strip() for part in SEGMENT_SPLIT_RE.split(normalized) if part.strip()]
    if not parts:
        return normalized, "", ""

    question = parts[0]
    answer = ""
    explanation_parts: list[str] = []

    for part in parts[1:]:
        answer_match = ANSWER_RE.match(part)
        if answer_match and not answer:
            answer = normalize_ox_answer(answer_match.group(1))
            tail = clean_text(part[answer_match.end() :]).strip(" :/-")
            if tail:
                explanation_parts.append(tail)
            continue

        explanation_match = EXPLANATION_RE.match(part)
        if explanation_match:
            tail = clean_text(explanation_match.group(1))
            if tail:
                explanation_parts.append(tail)
            continue

        if not answer:
            short_answer = normalize_ox_answer(part)
            if short_answer:
                answer = short_answer
                continue

        explanation_parts.append(part)

    return question, answer, "\n".join(explanation_parts).strip()


def parse_block_explanation(lines: list[str]) -> str:
    extra_lines: list[str] = []
    for line in lines[1:]:
        cleaned = clean_text(line)
        if not cleaned:
            continue

        explanation_match = EXPLANATION_RE.match(cleaned)
        if explanation_match:
            cleaned = clean_text(explanation_match.group(1))
        else:
            answer_match = ANSWER_RE.match(cleaned)
            if answer_match:
                cleaned = clean_text(cleaned[answer_match.end() :]).strip(" :/-")

        if cleaned:
            extra_lines.append(cleaned)

    return "\n".join(extra_lines).strip()


def parse_ox_text(path: Path) -> list[tuple[int, str, str, str]]:
    text = path.read_text(encoding="utf-8")
    matches = list(ENTRY_RE.finditer(text))
    parsed: list[tuple[int, str, str, str]] = []

    for index, match in enumerate(matches):
        qno = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if not block:
            continue

        lines = block.splitlines()
        header = lines[0] if lines else ""
        header_body = strip_header_prefix(header, qno)
        inline_question, inline_answer, inline_explanation = parse_inline_segments(header_body)

        question = clean_text(inline_question or header_body)
        answer = normalize_ox_answer(inline_answer)
        if not answer:
            answer_match = ANSWER_RE.search(block)
            if answer_match:
                answer = normalize_ox_answer(answer_match.group(1))
            else:
                inline_match = INLINE_ANSWER_RE.search(header)
                answer = normalize_ox_answer(inline_match.group(1) if inline_match else "")
        if not question or not answer:
            continue

        explanation = clean_text(inline_explanation)
        if not explanation:
            explanation = parse_block_explanation(lines)
        if not explanation:
            explanation = clean_text(block)

        parsed.append((qno, question, answer, explanation))

    return parsed


def ensure_ox_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_OX}" (
            ox\ubb38\uc81cid INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_QNO}" INTEGER NOT NULL,
            "{COL_SOURCE_QNO}" INTEGER NOT NULL DEFAULT 0,
            "{COL_STABLE_ID}" TEXT NOT NULL DEFAULT '',
            "{COL_QUESTION}" TEXT NOT NULL,
            "{COL_ANSWER}" TEXT NOT NULL,
            "{COL_EXPLANATION}" TEXT NOT NULL,
            UNIQUE ("{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
        )
        """
    )
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_OX}")')}
    if COL_SOURCE_QNO not in columns:
        conn.execute(
            f'ALTER TABLE "{TABLE_OX}" ADD COLUMN "{COL_SOURCE_QNO}" INTEGER NOT NULL DEFAULT 0'
        )
        conn.execute(
            f'UPDATE "{TABLE_OX}" SET "{COL_SOURCE_QNO}" = "{COL_QNO}" WHERE "{COL_SOURCE_QNO}" = 0'
        )
    if COL_STABLE_ID not in columns:
        conn.execute(
            f'ALTER TABLE "{TABLE_OX}" ADD COLUMN "{COL_STABLE_ID}" TEXT NOT NULL DEFAULT \'\''
        )
    rows = conn.execute(
        f'SELECT rowid, "{COL_SOURCE_QNO}", "{COL_QNO}", "{COL_QUESTION}", "{COL_STABLE_ID}" FROM "{TABLE_OX}"'
    ).fetchall()
    occurrence_map: dict[str, int] = {}
    for rowid, source_qno, qno, question, stable_id in rows:
        current = str(stable_id or "").strip()
        if current:
            continue
        source_value = int(source_qno or 0) or int(qno or 0)
        base = build_stable_id(source_value, str(question or ""), 1)
        occurrence_map[base] = occurrence_map.get(base, 0) + 1
        next_stable_id = build_stable_id(source_value, str(question or ""), occurrence_map[base])
        conn.execute(
            f'UPDATE "{TABLE_OX}" SET "{COL_STABLE_ID}" = ?, "{COL_SOURCE_QNO}" = ? WHERE rowid = ?',
            (next_stable_id, source_value, rowid),
        )
    conn.commit()


def import_ox_text(*, db_path: Path, year: int, subject: str, text_path: Path) -> dict[str, int]:
    records = parse_ox_text(text_path)
    if not records:
        raise ValueError(f"No parsable OX records found: {text_path}")

    conn = sqlite3.connect(db_path)
    try:
        ensure_ox_table(conn)
        conn.execute(
            f'DELETE FROM "{TABLE_OX}" WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?',
            (int(year), subject.strip()),
        )
        sql = f"""
            INSERT INTO "{TABLE_OX}"
            ("{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_SOURCE_QNO}", "{COL_STABLE_ID}", "{COL_QUESTION}", "{COL_ANSWER}", "{COL_EXPLANATION}")
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        updated = 0
        occurrence_map: dict[str, int] = {}
        for sequence, (source_qno, question, answer, explanation) in enumerate(records, start=1):
            base = build_stable_id(source_qno, question, 1)
            occurrence_map[base] = occurrence_map.get(base, 0) + 1
            stable_id = build_stable_id(source_qno, question, occurrence_map[base])
            cursor = conn.execute(
                sql,
                (
                    int(year),
                    subject.strip(),
                    sequence,
                    int(source_qno),
                    stable_id,
                    question,
                    answer,
                    explanation,
                ),
            )
            if cursor.rowcount and cursor.rowcount > 0:
                updated += int(cursor.rowcount)
        conn.commit()
    finally:
        conn.close()

    return {"parsed": len(records), "upserted": updated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import OX text file into 문제_OX table.")
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
        text_path = find_year_file(year_dir, f"{args.subject}ox.txt", kind="ox")

    result = import_ox_text(
        db_path=Path(args.db_path),
        year=int(args.year),
        subject=str(args.subject),
        text_path=text_path,
    )
    for key, value in result.items():
        print(f"{key}={value}")
    print(f"path={text_path}")


if __name__ == "__main__":
    main()
