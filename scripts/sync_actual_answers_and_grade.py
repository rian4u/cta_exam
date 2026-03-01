from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path


CIRCLED = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}


def normalize_answer(text: str) -> str:
    ordered: list[str] = []
    for ch in text or "":
        digit = CIRCLED.get(ch, ch if ch in "12345" else "")
        if digit and digit not in ordered:
            ordered.append(digit)
    return ",".join(ordered)


def question_table_meta(conn: sqlite3.Connection) -> tuple[str, list[str], dict[str, int]]:
    table_name = None
    for name, sql in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY rowid"):
        if not sql or name == "sqlite_sequence":
            continue
        if "문제지문" in sql and "답_배포" in sql:
            table_name = name
            break
    if not table_name:
        raise RuntimeError("문제 테이블을 찾지 못했습니다.")
    cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')]
    return table_name, cols, {name: idx for idx, name in enumerate(cols)}


def parse_actual_answers(path: Path) -> dict[tuple[str, int], str]:
    text = path.read_text(encoding="utf-8")
    current_subject = ""
    mapping: dict[tuple[str, int], str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("■"):
            subject = line[1:].strip()
            if ":" in subject:
                subject = subject.split(":", 1)[1].strip()
            current_subject = subject
            continue
        if not current_subject:
            continue

        starts = list(re.finditer(r"(\d{1,2})\s*:", line))
        for idx, match in enumerate(starts):
            qno = int(match.group(1))
            start = match.end()
            end = starts[idx + 1].start() if idx + 1 < len(starts) else len(line)
            chunk = line[start:end]
            answer = normalize_answer(chunk)
            if answer:
                mapping[(current_subject, qno)] = answer
    return mapping


def sync_distributed_answers(conn: sqlite3.Connection, year: int, txt_path: Path) -> tuple[int, int]:
    table_name, cols, idx = question_table_meta(conn)
    col_year = cols[idx["출제연도"]]
    col_subject = cols[idx["과목"]]
    col_qno = cols[idx["문제번호"]]
    col_dist = cols[idx["답_배포"]]

    mapping = parse_actual_answers(txt_path)
    updated = 0
    for (subject, qno), answer in mapping.items():
        cur = conn.execute(
            f'UPDATE "{table_name}" SET "{col_dist}" = ? WHERE "{col_year}" = ? AND "{col_subject}" = ? AND "{col_qno}" = ?',
            (answer, year, subject, qno),
        )
        updated += int(cur.rowcount or 0)
    return len(mapping), updated


def clean_explanation(text: str) -> str:
    text = re.sub(r"\[cite_start\]", "", text)
    text = re.sub(r"\[cite:\s*[\d,\s]+\]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_solution_text(path: Path) -> dict[int, tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    entry_re = re.compile(r"(?m)^\s*(?:#+\s*\[.*?\]\s*)?(\d{1,2})\.\s*")
    answer_line_re = re.compile(r"정답\s*:\s*([^\n\r]+)")

    entries = list(entry_re.finditer(text))
    parsed: dict[int, tuple[str, str]] = {}

    for idx, match in enumerate(entries):
        qno = int(match.group(1))
        start = match.start()
        end = entries[idx + 1].start() if idx + 1 < len(entries) else len(text)
        block = text[start:end].strip()
        answer_match = answer_line_re.search(block)
        if not answer_match:
            continue
        answer = normalize_answer(answer_match.group(1))
        if not answer:
            continue
        parsed[qno] = (answer, clean_explanation(block))
    return parsed


def import_solution(conn: sqlite3.Connection, year: int, subject: str, text_path: Path) -> dict[str, int]:
    table_name, cols, idx = question_table_meta(conn)
    col_year = cols[idx["출제연도"]]
    col_subject = cols[idx["과목"]]
    col_qno = cols[idx["문제번호"]]
    col_answer = cols[idx["답"]]
    col_dist = cols[idx["답_배포"]]
    col_expl = cols[idx["해설"]]
    col_answered = "답변여부"

    existing_cols = set(cols)
    if col_answered not in existing_cols:
        conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_answered}" INTEGER NOT NULL DEFAULT 0')
        cols = [row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')]

    records = parse_solution_text(text_path)
    updated = 0
    for qno, (answer, explanation) in sorted(records.items()):
        cur = conn.execute(
            f'UPDATE "{table_name}" SET "{col_answer}" = ?, "{col_expl}" = ?, "{col_answered}" = 1 '
            f'WHERE "{col_year}" = ? AND "{col_subject}" = ? AND "{col_qno}" = ?',
            (answer, explanation, year, subject, qno),
        )
        updated += int(cur.rowcount or 0)

    matched = 0
    mismatch = 0
    no_distributed = 0
    for answer, dist in conn.execute(
        f'SELECT "{col_answer}", "{col_dist}" FROM "{table_name}" '
        f'WHERE "{col_year}" = ? AND "{col_subject}" = ? ORDER BY "{col_qno}"',
        (year, subject),
    ):
        na = normalize_answer(answer or "")
        nd = normalize_answer(dist or "")
        if not nd:
            no_distributed += 1
        elif na == nd:
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


def grade_subject(conn: sqlite3.Connection, year: int, subject: str) -> dict[str, object]:
    table_name, cols, idx = question_table_meta(conn)
    col_year = cols[idx["출제연도"]]
    col_subject = cols[idx["과목"]]
    col_qno = cols[idx["문제번호"]]
    col_answer = cols[idx["답"]]
    col_dist = cols[idx["답_배포"]]

    rows = conn.execute(
        f'SELECT "{col_qno}", "{col_answer}", "{col_dist}" FROM "{table_name}" '
        f'WHERE "{col_year}" = ? AND "{col_subject}" = ? ORDER BY "{col_qno}"',
        (year, subject),
    ).fetchall()
    matched = 0
    mismatch = 0
    no_distributed = 0
    mismatches: list[str] = []
    for qno, answer, dist in rows:
        na = normalize_answer(answer or "")
        nd = normalize_answer(dist or "")
        if not nd:
            no_distributed += 1
        elif na == nd:
            matched += 1
        else:
            mismatch += 1
            mismatches.append(f"{qno}번({na or '-'} / {nd})")
    return {
        "total": len(rows),
        "matched": matched,
        "mismatch": mismatch,
        "no_distributed": no_distributed,
        "mismatches": mismatches,
    }


def subjects_for_year(conn: sqlite3.Connection, year: int) -> list[str]:
    table_name, cols, idx = question_table_meta(conn)
    col_year = cols[idx["출제연도"]]
    col_subject = cols[idx["과목"]]
    col_qno = cols[idx["문제번호"]]
    rows = conn.execute(
        f'SELECT "{col_subject}", MIN("{col_qno}") AS mn FROM "{table_name}" '
        f'WHERE "{col_year}" = ? GROUP BY "{col_subject}" ORDER BY mn, "{col_subject}"',
        (year,),
    ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="data/questions.db")
    parser.add_argument("--data-root", default="data")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    data_root = Path(args.data_root)

    conn = sqlite3.connect(db_path)
    try:
        print("[답_배포 동기화]")
        for year in (2023, 2024, 2025):
            txt_path = data_root / str(year) / "실제정답.txt"
            parsed, updated = sync_distributed_answers(conn, year, txt_path)
            print(f"{year}: parsed={parsed}, updated={updated}, source={txt_path}")

        print("\n[2024 풀이 재적재]")
        for subject in ("재정학", "세법학개론"):
            txt_path = data_root / "2024" / "풀이" / f"{subject}풀이.txt"
            result = import_solution(conn, 2024, subject, txt_path)
            print(
                f"2024 {subject}: parsed={result['parsed']}, updated={result['updated']}, "
                f"matched={result['matched']}, mismatch={result['mismatch']}, no_distributed={result['no_distributed']}"
            )

        conn.commit()

        print("\n[채점 결과]")
        for year, subjects in (
            (2024, ["재정학", "세법학개론"]),
            (2025, subjects_for_year(conn, 2025)),
        ):
            print(f"{year}:")
            for subject in subjects:
                result = grade_subject(conn, year, subject)
                print(
                    f"  {subject}: total={result['total']}, matched={result['matched']}, "
                    f"mismatch={result['mismatch']}, no_distributed={result['no_distributed']}"
                )
                if result["mismatches"]:
                    print(f"    mismatches: {', '.join(result['mismatches'])}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
