from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .repository import SQLiteRepository


@dataclass(slots=True)
class BuildResult:
    source_db: str
    target_db: str
    question_count: int
    ox_item_count: int


def _normalize_answer(value: str | None) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    for num in ("1", "2", "3", "4", "5"):
        if text.startswith(num):
            return num
    return text


def _read_source_questions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            exam_year,
            booklet_type,
            subject_name,
            subject_code,
            question_no_exam,
            question_no_subject,
            question_text,
            choices_json,
            official_answer,
            service_answer,
            explanation_text,
            updated_at
        FROM exam_question_bank
        ORDER BY exam_year, subject_code, question_no_exam,
                 CASE booklet_type WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 9 END,
                 id
        """
    ).fetchall()
    picked: dict[tuple[int, str, int], dict] = {}
    for row in rows:
        key = (int(row["exam_year"]), str(row["subject_code"]), int(row["question_no_exam"]))
        if key in picked:
            continue
        answer = _normalize_answer(str(row["service_answer"] or row["official_answer"] or ""))
        if not answer:
            continue
        choices_raw = str(row["choices_json"] or "[]")
        try:
            choices = json.loads(choices_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(choices, list) or len(choices) < 2:
            continue
        picked[key] = {
            "exam_year": int(row["exam_year"]),
            "subject_name": str(row["subject_name"] or row["subject_code"]),
            "subject_code": str(row["subject_code"]),
            "question_no_exam": int(row["question_no_exam"]),
            "question_no_subject": int(row["question_no_subject"] or 0),
            "question_text": str(row["question_text"] or ""),
            "choices_json": json.dumps(choices, ensure_ascii=False),
            "official_answer": str(row["official_answer"] or ""),
            "service_answer": answer,
            "explanation_text": str(row["explanation_text"] or ""),
            "updated_at": str(row["updated_at"] or datetime.utcnow().isoformat()),
        }
    return list(picked.values())


def _read_source_ox_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            exam_year,
            subject_code,
            question_no_exam,
            choice_no,
            choice_text,
            choice_explanation_text,
            expected_ox,
            judge_reason,
            updated_at
        FROM exam_choice_ox_bank
        WHERE is_ox_eligible = 1
        ORDER BY exam_year, subject_code, question_no_exam, choice_no, id
        """
    ).fetchall()
    picked: dict[tuple[int, str, int, int], dict] = {}
    for row in rows:
        expected_ox = str(row["expected_ox"] or "").strip().upper()
        if expected_ox not in {"O", "X"}:
            continue
        key = (
            int(row["exam_year"]),
            str(row["subject_code"]),
            int(row["question_no_exam"]),
            int(row["choice_no"]),
        )
        if key in picked:
            continue
        picked[key] = {
            "exam_year": int(row["exam_year"]),
            "subject_code": str(row["subject_code"]),
            "question_no_exam": int(row["question_no_exam"]),
            "choice_no": int(row["choice_no"]),
            "choice_text": str(row["choice_text"] or ""),
            "choice_explanation_text": str(row["choice_explanation_text"] or row["judge_reason"] or ""),
            "expected_ox": expected_ox,
            "judge_reason": str(row["judge_reason"] or ""),
            "updated_at": str(row["updated_at"] or datetime.utcnow().isoformat()),
        }
    return list(picked.values())


def build_service_db(source_db: str, target_db: str, overwrite: bool = True) -> BuildResult:
    source_path = Path(source_db)
    target_path = Path(target_db)
    if not source_path.exists():
        raise FileNotFoundError(f"Source DB not found: {source_path}")
    if target_path.exists() and not overwrite:
        raise FileExistsError(f"Target DB already exists: {target_path}")
    if target_path.exists() and overwrite:
        target_path.unlink()

    source_conn = sqlite3.connect(str(source_path))
    source_conn.row_factory = sqlite3.Row
    try:
        questions = _read_source_questions(source_conn)
        ox_items = _read_source_ox_items(source_conn)
    finally:
        source_conn.close()

    repo = SQLiteRepository(str(target_path), schema_profile="service")
    with repo._conn() as conn:  # noqa: SLF001
        conn.executemany(
            """
            INSERT INTO exam_question_bank (
                exam_year, session_no, booklet_type, subject_name, subject_code,
                question_no_exam, question_no_subject, question_text, choices_json,
                source_file, official_answer, service_answer, review_flag, review_reason,
                explanation_text, explanation_model, updated_at
            )
            VALUES (?, 0, 'A', ?, ?, ?, ?, ?, ?, '', ?, ?, 0, '', ?, 'service_import', ?)
            """,
            [
                (
                    q["exam_year"],
                    q["subject_name"],
                    q["subject_code"],
                    q["question_no_exam"],
                    q["question_no_subject"],
                    q["question_text"],
                    q["choices_json"],
                    q["official_answer"],
                    q["service_answer"],
                    q["explanation_text"],
                    q["updated_at"],
                )
                for q in questions
            ],
        )

        id_rows = conn.execute(
            "SELECT id, exam_year, subject_code, question_no_exam FROM exam_question_bank"
        ).fetchall()
        question_id_map = {
            (int(r["exam_year"]), str(r["subject_code"]), int(r["question_no_exam"])): int(r["id"]) for r in id_rows
        }
        conn.executemany(
            """
            INSERT INTO exam_choice_ox_bank (
                question_bank_id, exam_year, subject_code, question_no_exam,
                choice_no, choice_text, choice_explanation_text, is_ox_eligible,
                expected_ox, stem_polarity, judge_reason, judge_confidence, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, '', ?, 'service_import', ?)
            """,
            [
                (
                    question_id_map[(o["exam_year"], o["subject_code"], o["question_no_exam"])],
                    o["exam_year"],
                    o["subject_code"],
                    o["question_no_exam"],
                    o["choice_no"],
                    o["choice_text"],
                    o["choice_explanation_text"],
                    o["expected_ox"],
                    o["judge_reason"],
                    o["updated_at"],
                )
                for o in ox_items
                if (o["exam_year"], o["subject_code"], o["question_no_exam"]) in question_id_map
            ],
        )

    return BuildResult(
        source_db=str(source_path),
        target_db=str(target_path),
        question_count=len(questions),
        ox_item_count=len(ox_items),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deploy-ready service DB from local authoring DB.")
    parser.add_argument("--source-db", default="tax_exam.db")
    parser.add_argument("--target-db", default="tax_exam_service.db")
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args(argv)

    result = build_service_db(
        source_db=args.source_db,
        target_db=args.target_db,
        overwrite=not args.no_overwrite,
    )
    print(
        json.dumps(
            {
                "source_db": result.source_db,
                "target_db": result.target_db,
                "question_count": result.question_count,
                "ox_item_count": result.ox_item_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
