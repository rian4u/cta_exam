from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Keep source ASCII-only. Use unicode escapes for Korean labels.
K_QUESTION = "\ubb38\uc81c"  # 문제
K_ANSWER = "\ub2f5"  # 답
K_EXPLANATION = "\ud574\uc124"  # 해설

SUPPORTED_TYPE_LABELS = {
    "single_true": "\uc815\ub2f5 \uc120\ud0dd\ud615(\uc62e\uc740/\ub9de\ub294/\uc801\uc808\ud55c \uac83)",
    "single_false": "\uc624\ub2f5 \uc120\ud0dd\ud615(\uc62e\uc9c0 \uc54a\uc740/\ud2c0\ub9b0/\uc798\ubabb\ub41c \uac83)",
}

# Compact-token matching against whitespace-stripped stem text.
POSITIVE_STEM_TOKENS = (
    "\uc633\uc740\uac83",  # 옳은것
    "\ub9de\ub294\uac83",  # 맞는것
    "\uc801\uc808\ud55c\uac83",  # 적절한것
    "\ud0c0\ub2f9\ud55c\uac83",  # 타당한것
    "\uc62c\ubc14\ub978\uac83",  # 올바른것
    "\uac00\ub2a5\ud55c\uac83",  # 가능한것
    "\uc633\uc740\uc124\uba85",  # 옳은설명
    "\ub9de\ub294\uc124\uba85",  # 맞는설명
    "\uc801\uc808\ud55c\uc124\uba85",  # 적절한설명
    "\ud0c0\ub2f9\ud55c\uc124\uba85",  # 타당한설명
    "\uc62c\ubc14\ub978\uc124\uba85",  # 올바른설명
)

NEGATIVE_STEM_TOKENS = (
    "\uc633\uc9c0\uc54a\uc740\uac83",  # 옳지않은것
    "\ud2c0\ub9b0\uac83",  # 틀린것
    "\uc798\ubabb\ub41c\uac83",  # 잘못된것
    "\ubd80\uc801\uc808\ud55c\uac83",  # 부적절한것
    "\uc801\uc808\ud558\uc9c0\uc54a\uc740\uac83",  # 적절하지않은것
    "\ud0c0\ub2f9\ud558\uc9c0\uc54a\uc740\uac83",  # 타당하지않은것
    "\uc544\ub2cc\uac83",  # 아닌것
    "\uc633\uc9c0\uc54a\uc740\uc124\uba85",  # 옳지않은설명
    "\ud2c0\ub9b0\uc124\uba85",  # 틀린설명
    "\uc798\ubabb\ub41c\uc124\uba85",  # 잘못된설명
)

# Explicit exclusions where option-level OX conversion is usually unsafe.
UNSUPPORTED_STEM_TOKENS = (
    "\ubaa8\ub450\uace0\ub978",  # 모두고른
    "\uace0\ub978\uac83",  # 고른것
    "\uc5f0\uacb0\ub41c\uac83",  # 연결된것
    "\uc9dd\uc9c0\uc740\uac83",  # 짝지은것
    "\uc21c\uc11c",  # 순서
    "\uac1c\uc218",  # 개수
    "\ud569\uacc4",  # 합계
    "\uae08\uc561",  # 금액
    "\uacc4\uc0b0",  # 계산
    "\uc870\ud569",  # 조합
)

CIRCLE_TO_DIGIT = str.maketrans(
    {
        "\u2460": "1",
        "\u2461": "2",
        "\u2462": "3",
        "\u2463": "4",
        "\u2464": "5",
    }
)


@dataclass
class QuestionSchema:
    table: str
    year: str
    subject: str
    qno: str
    stem: str
    options: list[str]
    answer: str
    explanation: str


@dataclass
class OxSchema:
    table: str
    year: str
    subject: str
    qno: str
    question: str
    answer: str
    explanation: str


@dataclass
class QuestionRow:
    year: int
    subject: str
    question_no: int
    stem: str
    options: list[str]
    answer: str
    explanation: str


@dataclass
class BuildStats:
    total_question_rows: int = 0
    eligible_question_rows: int = 0
    generated_ox_rows: int = 0
    skip_no_answer: int = 0
    skip_unsupported_type: int = 0
    skip_empty_options: int = 0
    by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_group_rows: dict[tuple[int, str], int] = field(default_factory=dict)


def qi(name: str) -> str:
    return f'"{name.replace("\"", "\"\"")}"'


def compact_spaces(value: str) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").replace("\r", "\n").split()).strip()


def compact_no_space(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def normalize_explanation(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def parse_answer_set(raw: str) -> set[str]:
    normalized = str(raw or "").translate(CIRCLE_TO_DIGIT)
    return set(re.findall(r"[1-5]", normalized))


def load_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({qi(table)})")]


def find_question_schema(conn: sqlite3.Connection) -> QuestionSchema:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        )
    ]
    best_table = ""
    best_cols: list[str] = []
    best_score = -1

    for table in tables:
        cols = load_table_columns(conn, table)
        if len(cols) < 11:
            continue
        option_suffix_count = sum(1 for col in cols if any(col.endswith(f"_{n}") for n in range(1, 6)))
        score = len(cols) + option_suffix_count * 10
        if score > best_score:
            best_score = score
            best_table = table
            best_cols = cols

    if not best_table:
        raise RuntimeError("Could not find question table.")

    if len(best_cols) < 13:
        raise RuntimeError(f"Question table schema is too short: {best_table} / {best_cols}")

    return QuestionSchema(
        table=best_table,
        year=best_cols[1],
        subject=best_cols[2],
        qno=best_cols[3],
        stem=best_cols[4],
        options=[best_cols[5], best_cols[6], best_cols[7], best_cols[8], best_cols[9]],
        answer=best_cols[10],
        explanation=best_cols[12],
    )


def ensure_and_find_ox_schema(conn: sqlite3.Connection, qschema: QuestionSchema) -> OxSchema:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        )
    ]

    ox_table = ""
    ox_cols: list[str] = []
    for table in tables:
        cols = load_table_columns(conn, table)
        if len(cols) < 7:
            continue
        if table == f"{qschema.table}_OX" or "OX" in table.upper():
            ox_table = table
            ox_cols = cols
            break

    if not ox_table:
        ox_table = f"{qschema.table}_OX"
        ox_id_col = f"ox{K_QUESTION}id"
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {qi(ox_table)} (
                {qi(ox_id_col)} INTEGER PRIMARY KEY AUTOINCREMENT,
                {qi(qschema.year)} INTEGER NOT NULL,
                {qi(qschema.subject)} TEXT NOT NULL,
                {qi(qschema.qno)} INTEGER NOT NULL,
                {qi(K_QUESTION)} TEXT NOT NULL,
                {qi(K_ANSWER)} TEXT NOT NULL,
                {qi(K_EXPLANATION)} TEXT NOT NULL,
                UNIQUE ({qi(qschema.year)}, {qi(qschema.subject)}, {qi(qschema.qno)})
            )
            """
        )
        conn.commit()
        ox_cols = load_table_columns(conn, ox_table)

    if len(ox_cols) < 7:
        raise RuntimeError(f"OX table schema is too short: {ox_table} / {ox_cols}")

    return OxSchema(
        table=ox_table,
        year=ox_cols[1],
        subject=ox_cols[2],
        qno=ox_cols[3],
        question=ox_cols[4],
        answer=ox_cols[5],
        explanation=ox_cols[6],
    )


def fetch_question_rows(
    conn: sqlite3.Connection,
    *,
    schema: QuestionSchema,
    years: list[int],
    subjects: list[str] | None = None,
) -> list[QuestionRow]:
    if not years:
        return []

    year_placeholders = ", ".join("?" for _ in years)
    params: list[object] = list(years)
    filters = [f"{qi(schema.year)} IN ({year_placeholders})"]

    if subjects:
        subject_placeholders = ", ".join("?" for _ in subjects)
        filters.append(f"{qi(schema.subject)} IN ({subject_placeholders})")
        params.extend(subjects)

    select_cols = [
        qi(schema.year),
        qi(schema.subject),
        qi(schema.qno),
        qi(schema.stem),
        *(qi(col) for col in schema.options),
        qi(schema.answer),
        qi(schema.explanation),
    ]
    sql = (
        f"SELECT {', '.join(select_cols)} FROM {qi(schema.table)} "
        f"WHERE {' AND '.join(filters)} "
        f"ORDER BY {qi(schema.year)} ASC, {qi(schema.subject)} ASC, {qi(schema.qno)} ASC"
    )
    rows = conn.execute(sql, params).fetchall()

    parsed: list[QuestionRow] = []
    for row in rows:
        year = int(row[0])
        subject = str(row[1])
        qno = int(row[2])
        stem = compact_spaces(row[3])
        option_values = [compact_spaces(value) for value in row[4:9]]
        answer = str(row[9] or "").strip()
        explanation = normalize_explanation(row[10])
        parsed.append(
            QuestionRow(
                year=year,
                subject=subject,
                question_no=qno,
                stem=stem,
                options=option_values,
                answer=answer,
                explanation=explanation,
            )
        )
    return parsed


def classify_ox_extractable_type(stem: str) -> str | None:
    compact = compact_no_space(stem)
    if not compact:
        return None

    if any(token in compact for token in UNSUPPORTED_STEM_TOKENS):
        return None

    # Negative first: e.g. "옳지 않은 것은?" should become false-selection type.
    if any(token in compact for token in NEGATIVE_STEM_TOKENS):
        return "single_false"
    if any(token in compact for token in POSITIVE_STEM_TOKENS):
        return "single_true"
    return None


def build_ox_answer(option_no: int, answer_set: set[str], stem_type: str) -> str:
    selected = str(option_no) in answer_set
    if stem_type == "single_false":
        return "X" if selected else "O"
    return "O" if selected else "X"


def build_ox_question_text(original_qno: int, option_no: int, option_text: str) -> str:
    return f"{original_qno}\ubc88 \ubcf4\uae30 {option_no}. {option_text}"


def build_ox_explanation_text(
    *,
    original_qno: int,
    option_no: int,
    stem_type: str,
    ox_answer: str,
    answer_set: set[str],
    original_explanation: str,
) -> str:
    answer_label = ", ".join(sorted(answer_set)) if answer_set else "\uc5c6\uc74c"
    type_label = SUPPORTED_TYPE_LABELS.get(stem_type, stem_type)
    lines = [
        f"\uc6d0\ubb38 {original_qno}\ubc88 {option_no}\ubc88 \ubcf4\uae30 \ud310\ub2e8: {ox_answer}",
        f"\ucd94\ucd9c \uc720\ud615: {type_label}",
        f"\uc6d0\ubb38 \uc815\ub2f5 \ubcf4\uae30: {answer_label}",
    ]
    if original_explanation:
        lines.extend(["", "\uc6d0\ubb38 \ud574\uc124:", original_explanation])
    return "\n".join(lines).strip()


def rebuild_ox_rows(
    conn: sqlite3.Connection,
    *,
    years: list[int],
    subjects: list[str] | None = None,
) -> BuildStats:
    qschema = find_question_schema(conn)
    oxschema = ensure_and_find_ox_schema(conn, qschema)
    questions = fetch_question_rows(conn, schema=qschema, years=years, subjects=subjects)

    grouped: dict[tuple[int, str], list[QuestionRow]] = defaultdict(list)
    for row in questions:
        grouped[(row.year, row.subject)].append(row)

    stats = BuildStats(total_question_rows=len(questions))

    for (year, subject), rows in grouped.items():
        conn.execute(
            f"DELETE FROM {qi(oxschema.table)} WHERE {qi(oxschema.year)} = ? AND {qi(oxschema.subject)} = ?",
            (year, subject),
        )

        insert_values: list[tuple[object, ...]] = []
        ox_no = 1

        for question in rows:
            answer_set = parse_answer_set(question.answer)
            if not answer_set:
                stats.skip_no_answer += 1
                continue

            stem_type = classify_ox_extractable_type(question.stem)
            if stem_type is None:
                stats.skip_unsupported_type += 1
                continue

            options = [(idx, text) for idx, text in enumerate(question.options, start=1) if text]
            if not options:
                stats.skip_empty_options += 1
                continue

            stats.eligible_question_rows += 1
            stats.by_type[stem_type] += 1

            for option_no, option_text in options:
                ox_answer = build_ox_answer(option_no, answer_set, stem_type)
                ox_question = build_ox_question_text(question.question_no, option_no, option_text)
                ox_explanation = build_ox_explanation_text(
                    original_qno=question.question_no,
                    option_no=option_no,
                    stem_type=stem_type,
                    ox_answer=ox_answer,
                    answer_set=answer_set,
                    original_explanation=question.explanation,
                )
                insert_values.append(
                    (
                        year,
                        subject,
                        ox_no,
                        ox_question,
                        ox_answer,
                        ox_explanation,
                    )
                )
                ox_no += 1

        if insert_values:
            conn.executemany(
                f"""
                INSERT INTO {qi(oxschema.table)}
                ({qi(oxschema.year)}, {qi(oxschema.subject)}, {qi(oxschema.qno)}, {qi(oxschema.question)}, {qi(oxschema.answer)}, {qi(oxschema.explanation)})
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                insert_values,
            )
        stats.by_group_rows[(year, subject)] = len(insert_values)
        stats.generated_ox_rows += len(insert_values)

    conn.commit()
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build OX rows from question table using only OX-safe stem types."
    )
    parser.add_argument("--db-path", default="data/questions.db", help="SQLite DB path")
    parser.add_argument("--years", nargs="+", type=int, default=[2023, 2024, 2025], help="Target years")
    parser.add_argument("--subjects", nargs="*", default=None, help="Optional subject whitelist")
    return parser.parse_args()


def print_summary(stats: BuildStats) -> None:
    print("OX rebuild complete.")
    print(f"- total question rows scanned: {stats.total_question_rows}")
    print(f"- eligible question rows: {stats.eligible_question_rows}")
    print(f"- generated OX rows: {stats.generated_ox_rows}")
    print("- supported extractable types:")
    print(f"  - single_true: {stats.by_type.get('single_true', 0)}")
    print(f"  - single_false: {stats.by_type.get('single_false', 0)}")
    print("- skipped question rows:")
    print(f"  - unsupported stem type: {stats.skip_unsupported_type}")
    print(f"  - empty answer: {stats.skip_no_answer}")
    print(f"  - empty options: {stats.skip_empty_options}")
    print("- rows by year/subject:")
    for (year, subject), count in sorted(stats.by_group_rows.items(), key=lambda item: (item[0][0], item[0][1])):
        print(f"  - {year} {subject}: {count}")


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        stats = rebuild_ox_rows(conn, years=list(args.years), subjects=args.subjects)
    finally:
        conn.close()

    print_summary(stats)


if __name__ == "__main__":
    main()
