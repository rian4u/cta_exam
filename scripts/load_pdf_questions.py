from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

from data_paths import list_year_pdfs
from fill_missing_answers_gemini import ensure_answered_column, enrich_missing_answers, load_api_key


FIRST_SESSION_SUBJECTS = ("\uc7ac\uc815\ud559", "\uc138\ubc95\ud559\uac1c\ub860")
SECOND_SESSION_BASE_SUBJECT = "\ud68c\uacc4\ud559\uac1c\ub860"
OPTIONAL_SUBJECTS = {"\uc0c1\ubc95", "\ubbfc\ubc95", "\ud589\uc815\uc18c\uc1a1\ubc95"}


def load_base_parser_module() -> ModuleType:
    script_path = Path(__file__).resolve().parent / "load_2025_questions.py"
    spec = importlib.util.spec_from_file_location("load_2025_questions_base", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load parser module from: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def find_single_session_pdf(year_dir: Path, token: str) -> Path:
    files = [path for path in list_year_pdfs(year_dir) if token in path.name]
    if len(files) != 1:
        names = [path.name for path in files]
        raise FileNotFoundError(f"[{year_dir.name}] '{token}' PDF expected 1, found {len(files)}: {names}")
    return files[0]


def find_second_session_pdfs(year_dir: Path) -> list[Path]:
    files = sorted(path for path in list_year_pdfs(year_dir) if "2\uad50\uc2dc" in path.name)
    if not files:
        raise FileNotFoundError(f"[{year_dir.name}] no 2교시 PDFs found")
    return files


def extract_optional_subject_from_filename(pdf_path: Path) -> str:
    match = re.search(r"\(([^)]+)\)", pdf_path.stem)
    if not match:
        raise ValueError(f"Cannot find optional subject in filename: {pdf_path.name}")
    subject = match.group(1).strip()
    if subject not in OPTIONAL_SUBJECTS:
        raise ValueError(f"Unexpected optional subject '{subject}' in: {pdf_path.name}")
    return subject


def build_year_rows(base: ModuleType, year_dir: Path, year: int) -> list:
    records: dict[tuple[int, str, int], object] = {}

    first_pdf = find_single_session_pdf(year_dir, "1\uad50\uc2dc")
    first_questions = base.parse_exam_pdf(first_pdf)
    for number, parsed in first_questions.items():
        subject = FIRST_SESSION_SUBJECTS[0] if number <= 40 else FIRST_SESSION_SUBJECTS[1]
        stem = str(parsed["stem"])
        options = dict(parsed["options"])
        stem_html = str(parsed.get("stem_html") or "")
        options_html = dict(parsed.get("options_html") or {})

        stem, options, stem_html, options_html = base.repair_parsed_question_text(
            year, subject, number, stem, options, stem_html, options_html
        )
        render_payload = json.dumps(
            {
                "stem_html": stem_html,
                "options_html": [
                    options_html["1"],
                    options_html["2"],
                    options_html["3"],
                    options_html["4"],
                    options_html["5"],
                ],
            },
            ensure_ascii=False,
        )
        key = (year, subject, int(number))
        records[key] = base.QuestionRow(
            year,
            subject,
            int(number),
            stem,
            options["1"],
            options["2"],
            options["3"],
            options["4"],
            options["5"],
            "",
            "",
            "",
            render_payload,
        )

    for second_pdf in find_second_session_pdfs(year_dir):
        optional_subject = extract_optional_subject_from_filename(second_pdf)
        second_questions = base.parse_exam_pdf(second_pdf)
        for number, parsed in second_questions.items():
            subject = SECOND_SESSION_BASE_SUBJECT if number <= 40 else optional_subject
            stem = str(parsed["stem"])
            options = dict(parsed["options"])
            stem_html = str(parsed.get("stem_html") or "")
            options_html = dict(parsed.get("options_html") or {})

            stem, options, stem_html, options_html = base.repair_parsed_question_text(
                year, subject, number, stem, options, stem_html, options_html
            )
            render_payload = json.dumps(
                {
                    "stem_html": stem_html,
                    "options_html": [
                        options_html["1"],
                        options_html["2"],
                        options_html["3"],
                        options_html["4"],
                        options_html["5"],
                    ],
                },
                ensure_ascii=False,
            )
            key = (year, subject, int(number))
            if subject == SECOND_SESSION_BASE_SUBJECT and key in records:
                continue
            records[key] = base.QuestionRow(
                year,
                subject,
                int(number),
                stem,
                options["1"],
                options["2"],
                options["3"],
                options["4"],
                options["5"],
                "",
                "",
                "",
                render_payload,
            )

    return sorted(
        records.values(),
        key=lambda row: (row.출제연도, row.과목, row.문제번호),
    )


def print_summary(rows: list) -> None:
    summary: dict[int, dict[str, int]] = {}
    for row in rows:
        by_year = summary.setdefault(int(row.출제연도), {})
        by_year[row.과목] = by_year.get(row.과목, 0) + 1

    total = len(rows)
    print(f"Loaded rows: {total}")
    for year in sorted(summary):
        print(f"[{year}]")
        for subject in sorted(summary[year]):
            print(f"  - {subject}: {summary[year][subject]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load tax exam questions from PDF only (no answers/explanations)."
    )
    parser.add_argument("--data-root", default="data", help="Root data directory that contains year folders.")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2021, 2022, 2023, 2024],
        help="Years to load.",
    )
    parser.add_argument("--db-path", default="data/questions.db", help="SQLite DB path.")
    parser.add_argument(
        "--gemini-fill-missing",
        action="store_true",
        help="After PDF load, fill missing answers/explanations via Gemini API.",
    )
    parser.add_argument("--gemini-api-key", default="", help="Gemini API key.")
    parser.add_argument(
        "--gemini-api-key-file",
        default="config/gemini_api_key.txt",
        help="Gemini API key file path (used if --gemini-api-key is empty).",
    )
    parser.add_argument("--gemini-model", default="gemini-1.5-pro", help="Gemini model name.")
    parser.add_argument(
        "--gemini-api-url",
        default="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        help="Gemini API endpoint template.",
    )
    parser.add_argument("--gemini-batch-size", type=int, default=10, help="Gemini request batch size.")
    parser.add_argument("--gemini-max-batches", type=int, default=0, help="0 means process all batches.")
    parser.add_argument("--gemini-sleep-sec", type=float, default=1.0, help="Sleep seconds between Gemini batches.")
    parser.add_argument("--gemini-retries", type=int, default=2, help="Retries per Gemini batch.")
    args = parser.parse_args()

    base = load_base_parser_module()
    data_root = Path(args.data_root)
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list = []
    for year in args.years:
        year_dir = data_root / str(year)
        if not year_dir.exists():
            raise FileNotFoundError(f"Year directory not found: {year_dir}")
        print(f"Parsing year {year} from {year_dir} ...")
        year_rows = build_year_rows(base, year_dir, year)
        print(f"  parsed rows: {len(year_rows)}")
        all_rows.extend(year_rows)

    conn = sqlite3.connect(db_path)
    try:
        base.ensure_schema(conn)
        ensure_answered_column(conn)
        base.upsert_questions(conn, all_rows)
        conn.commit()
    finally:
        conn.close()

    print(f"DB upsert complete: {db_path}")
    print_summary(all_rows)

    if args.gemini_fill_missing:
        api_key = load_api_key(
            args.gemini_api_key,
            Path(args.gemini_api_key_file) if args.gemini_api_key_file else None,
        )
        enrich_missing_answers(
            db_path=db_path,
            years=list(args.years),
            api_key=api_key,
            model=args.gemini_model,
            api_url=args.gemini_api_url,
            batch_size=args.gemini_batch_size,
            max_batches=args.gemini_max_batches,
            sleep_sec=args.gemini_sleep_sec,
            retries=args.gemini_retries,
        )


if __name__ == "__main__":
    main()
