from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

TABLE_QUESTIONS = "문제"
COL_YEAR = "출제연도"
COL_SUBJECT = "과목"
COL_QNO = "문제번호"
COL_STEM = "문제지문"
COL_OPT_1 = "보기_1"
COL_OPT_2 = "보기_2"
COL_OPT_3 = "보기_3"
COL_OPT_4 = "보기_4"
COL_OPT_5 = "보기_5"
COL_ANSWER = "답"
COL_EXPLANATION = "해설"
COL_ANSWERED = "답변여부"

DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_BATCH_SIZE = 10

SECTION_HEADER_RE = re.compile(r"(?m)^\s*(\d{4})년\s+(.+?)\s+(\d+)번\s+문제\s*$")
ANSWER_RE = re.compile(r"(?m)^\s*정답\s*[:：]?\s*([①②③④⑤1-5])\s*$")
TOPIC_RE = re.compile(r"(?m)^\s*주제\s*[:：]\s*(.+?)\s*$")
EXPLANATION_RE = re.compile(r"(?ms)^\s*해설(?:\s*\(.*?\))?\s*:?\s*(.*)$")

CIRCLE_TO_DIGIT = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
DIGIT_TO_CIRCLE = {"1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤"}


@dataclass
class QuestionRecord:
    year: int
    subject: str
    question_no: int
    stem: str
    options: list[str]


def normalize_answer_token(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return ""
    if value in CIRCLE_TO_DIGIT:
        return CIRCLE_TO_DIGIT[value]
    if value in DIGIT_TO_CIRCLE:
        return value
    return ""


def load_api_key(direct_value: str, key_file: Path | None) -> str:
    if direct_value.strip():
        return direct_value.strip()
    if key_file and key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


def ensure_answered_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_QUESTIONS}")')}
    if COL_ANSWERED not in columns:
        conn.execute(
            f'ALTER TABLE "{TABLE_QUESTIONS}" ADD COLUMN "{COL_ANSWERED}" INTEGER NOT NULL DEFAULT 0'
        )
    conn.execute(f'UPDATE "{TABLE_QUESTIONS}" SET "{COL_ANSWERED}" = 0 WHERE "{COL_ANSWERED}" IS NULL')
    conn.commit()


def fetch_missing_records(
    conn: sqlite3.Connection,
    *,
    years: list[int],
    subject: str = "",
    qno_start: int = 0,
    qno_end: int = 0,
    limit: int = 0,
) -> list[QuestionRecord]:
    placeholders = ", ".join("?" for _ in years)
    where_parts = [f'"{COL_YEAR}" IN ({placeholders})', f'COALESCE("{COL_ANSWERED}", 0) = 0']
    params: list[object] = list(years)

    normalized_subject = subject.strip()
    if normalized_subject:
        where_parts.append(f'"{COL_SUBJECT}" = ?')
        params.append(normalized_subject)
    if qno_start > 0:
        where_parts.append(f'"{COL_QNO}" >= ?')
        params.append(qno_start)
    if qno_end > 0:
        where_parts.append(f'"{COL_QNO}" <= ?')
        params.append(qno_end)

    sql = f"""
        SELECT
            "{COL_YEAR}",
            "{COL_SUBJECT}",
            "{COL_QNO}",
            "{COL_STEM}",
            "{COL_OPT_1}",
            "{COL_OPT_2}",
            "{COL_OPT_3}",
            "{COL_OPT_4}",
            "{COL_OPT_5}"
        FROM "{TABLE_QUESTIONS}"
        WHERE {" AND ".join(where_parts)}
        ORDER BY "{COL_YEAR}" ASC, "{COL_SUBJECT}" ASC, "{COL_QNO}" ASC
    """
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql, params).fetchall()
    results: list[QuestionRecord] = []
    for row in rows:
        year, subject_value, question_no, stem, o1, o2, o3, o4, o5 = row
        results.append(
            QuestionRecord(
                year=int(year),
                subject=str(subject_value or "").strip(),
                question_no=int(question_no),
                stem=str(stem or "").strip(),
                options=[
                    str(o1 or "").strip(),
                    str(o2 or "").strip(),
                    str(o3 or "").strip(),
                    str(o4 or "").strip(),
                    str(o5 or "").strip(),
                ],
            )
        )
    return results


def count_missing_records(
    conn: sqlite3.Connection,
    *,
    years: list[int],
    subject: str = "",
    qno_start: int = 0,
    qno_end: int = 0,
) -> int:
    placeholders = ", ".join("?" for _ in years)
    where_parts = [f'"{COL_YEAR}" IN ({placeholders})', f'COALESCE("{COL_ANSWERED}", 0) = 0']
    params: list[object] = list(years)

    normalized_subject = subject.strip()
    if normalized_subject:
        where_parts.append(f'"{COL_SUBJECT}" = ?')
        params.append(normalized_subject)
    if qno_start > 0:
        where_parts.append(f'"{COL_QNO}" >= ?')
        params.append(qno_start)
    if qno_end > 0:
        where_parts.append(f'"{COL_QNO}" <= ?')
        params.append(qno_end)

    sql = f'SELECT COUNT(*) FROM "{TABLE_QUESTIONS}" WHERE {" AND ".join(where_parts)}'
    return int(conn.execute(sql, params).fetchone()[0])


def build_prompt(records: list[QuestionRecord]) -> str:
    blocks: list[str] = []
    for record in records:
        option_lines = [
            f"① {record.options[0]}",
            f"② {record.options[1]}",
            f"③ {record.options[2]}",
            f"④ {record.options[3]}",
            f"⑤ {record.options[4]}",
        ]
        blocks.append(
            "\n".join(
                [
                    f"{record.year}년 {record.subject} {record.question_no}번 문제",
                    "문제",
                    record.stem,
                    "보기",
                    *option_lines,
                ]
            )
        )

    instruction = """
너는 세무사 1차 시험 문제 해설 작성 도우미다.
반드시 순수 텍스트로만 답하라. 마크다운 기호(*, -, #, ```), JSON, 코드블록을 사용하지 마라.
아래 각 문제에 대해 반드시 다음 형식을 정확히 지켜라.

형식:
2025년 재정학 7번 문제
정답 ③
주제 : 재화와 용역의 공급시기
해설
충분히 상세한 해설 작성
각 보기별 정답/오답 사유 작성

추가 규칙:
1) 정답 줄은 반드시 '정답 ①~⑤' 형식.
2) 계산문제는 계산과정을 충분히 상세히 작성하고 보기별 해설은 생략 가능.
3) 계산문제가 아니면 보기 1~5 각각에 대해 왜 정답/오답인지 설명.
4) 해설은 짧게 쓰지 말고, 개념/판단 근거/오답 원인을 충분히 작성.
5) 입력된 문제 순서를 그대로 유지해서 출력.
6) 문제마다 반드시 '주제 : ...' 한 줄을 포함.
"""
    return f"{instruction.strip()}\n\n입력 문제 목록\n\n{'\n\n'.join(blocks)}"


def call_gemini_text(
    *,
    api_key: str,
    model: str,
    api_url: str,
    prompt: str,
    timeout_sec: int = 120,
) -> str:
    endpoint = api_url.format(model=model) if "{model}" in api_url else api_url
    sep = "&" if "?" in endpoint else "?"
    endpoint = f"{endpoint}{sep}key={urllib.parse.quote(api_key)}"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API HTTP {error.code}: {details}") from error

    payload = json.loads(raw)
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
        if texts:
            return "\n".join(texts).strip()
    raise RuntimeError(f"Gemini response has no text candidates: {raw}")


def parse_gemini_response(text: str) -> dict[tuple[int, str, int], tuple[str, str]]:
    matches = list(SECTION_HEADER_RE.finditer(text))
    if not matches:
        raise ValueError("Could not find question sections in Gemini response.")

    parsed: dict[tuple[int, str, int], tuple[str, str]] = {}
    for index, match in enumerate(matches):
        year = int(match.group(1))
        subject = re.sub(r"\s+", " ", match.group(2).strip())
        question_no = int(match.group(3))
        section_start = match.end()
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[section_start:section_end].strip()

        answer_match = ANSWER_RE.search(section)
        topic_match = TOPIC_RE.search(section)
        explanation_match = EXPLANATION_RE.search(section)

        answer_digit = normalize_answer_token(answer_match.group(1) if answer_match else "")
        if not answer_digit:
            continue

        topic = topic_match.group(1).strip() if topic_match else ""
        explanation_body = explanation_match.group(1).strip() if explanation_match else ""
        if not explanation_body:
            continue

        explanation = f"주제 : {topic}\n\n{explanation_body}" if topic else explanation_body
        parsed[(year, subject, question_no)] = (answer_digit, explanation)
    return parsed


def update_answers(
    conn: sqlite3.Connection,
    *,
    updates: dict[tuple[int, str, int], tuple[str, str]],
) -> int:
    if not updates:
        return 0
    sql = f"""
        UPDATE "{TABLE_QUESTIONS}"
        SET "{COL_ANSWER}" = ?, "{COL_EXPLANATION}" = ?, "{COL_ANSWERED}" = 1
        WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ? AND "{COL_QNO}" = ?
    """
    count = 0
    for (year, subject, question_no), (answer, explanation) in updates.items():
        cursor = conn.execute(sql, (answer, explanation, year, subject, question_no))
        if cursor.rowcount and cursor.rowcount > 0:
            count += int(cursor.rowcount)
    conn.commit()
    return count


def enrich_missing_answers(
    *,
    db_path: Path,
    years: list[int],
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    api_url: str = DEFAULT_GEMINI_URL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = 0,
    sleep_sec: float = 1.0,
    retries: int = 2,
    timeout_sec: int = 120,
    subject: str = "",
    qno_start: int = 0,
    qno_end: int = 0,
) -> None:
    if not api_key.strip():
        raise ValueError("Gemini API key is required.")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if not years:
        raise ValueError("At least one year is required.")
    if qno_start > 0 and qno_end > 0 and qno_start > qno_end:
        raise ValueError("qno_start must be <= qno_end")

    conn = sqlite3.connect(db_path)
    try:
        ensure_answered_column(conn)
        initial_missing = count_missing_records(
            conn,
            years=years,
            subject=subject,
            qno_start=qno_start,
            qno_end=qno_end,
        )
        if initial_missing == 0:
            print("No missing records found.")
            return
        print(f"Missing records: {initial_missing}")

        batch_index = 0
        total_updated = 0
        while True:
            if max_batches > 0 and batch_index >= max_batches:
                break
            batch = fetch_missing_records(
                conn,
                years=years,
                subject=subject,
                qno_start=qno_start,
                qno_end=qno_end,
                limit=batch_size,
            )
            if not batch:
                break
            batch_index += 1
            print(f"[Batch {batch_index}] Requesting {len(batch)} questions ...")

            prompt = build_prompt(batch)
            parsed_updates: dict[tuple[int, str, int], tuple[str, str]] = {}
            last_error: Exception | None = None

            for attempt in range(1, retries + 2):
                try:
                    response_text = call_gemini_text(
                        api_key=api_key,
                        model=model,
                        api_url=api_url,
                        prompt=prompt,
                        timeout_sec=timeout_sec,
                    )
                    candidate_updates = parse_gemini_response(response_text)
                    expected_keys = {
                        (item.year, re.sub(r"\s+", " ", item.subject.strip()), item.question_no) for item in batch
                    }
                    parsed_updates = {
                        key: value for key, value in candidate_updates.items() if key in expected_keys
                    }
                    if len(parsed_updates) == 0:
                        raise RuntimeError("Parsed 0 valid updates from Gemini response.")
                    break
                except Exception as error:  # noqa: BLE001
                    last_error = error
                    print(f"[Batch {batch_index}] Attempt {attempt} failed: {error}")
                    if attempt >= retries + 1:
                        raise
                    time.sleep(1.0)

            if last_error and not parsed_updates:
                raise last_error

            updated = update_answers(conn, updates=parsed_updates)
            total_updated += updated
            unresolved = len(batch) - len(parsed_updates)
            remaining = count_missing_records(
                conn,
                years=years,
                subject=subject,
                qno_start=qno_start,
                qno_end=qno_end,
            )
            print(f"[Batch {batch_index}] Updated={updated}, unresolved={unresolved}, remaining={remaining}")
            if sleep_sec > 0:
                time.sleep(sleep_sec)

        print(f"Done. Total updated records: {total_updated}")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill missing answers/explanations in DB using Gemini API in sequential batches."
    )
    parser.add_argument("--db-path", default="data/questions.db", help="SQLite DB path")
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Target years")
    parser.add_argument("--api-key", default="", help="Gemini API key")
    parser.add_argument(
        "--api-key-file",
        default="config/gemini_api_key.txt",
        help="Path to Gemini API key file (used when --api-key is empty)",
    )
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL, help="Gemini model name")
    parser.add_argument("--api-url", default=DEFAULT_GEMINI_URL, help="Gemini API endpoint template")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size per request")
    parser.add_argument("--max-batches", type=int, default=0, help="Max batches (0 means all)")
    parser.add_argument("--sleep-sec", type=float, default=1.0, help="Sleep seconds between batches")
    parser.add_argument("--retries", type=int, default=2, help="Retries per batch on API/parse failure")
    parser.add_argument("--timeout-sec", type=int, default=120, help="HTTP read timeout seconds")
    parser.add_argument("--subject", default="", help="Optional subject filter (exact match)")
    parser.add_argument("--qno-start", type=int, default=0, help="Optional minimum question number")
    parser.add_argument("--qno-end", type=int, default=0, help="Optional maximum question number")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    api_key = load_api_key(args.api_key, Path(args.api_key_file) if args.api_key_file else None)
    enrich_missing_answers(
        db_path=db_path,
        years=args.years,
        api_key=api_key,
        model=args.model,
        api_url=args.api_url,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        sleep_sec=args.sleep_sec,
        retries=args.retries,
        timeout_sec=args.timeout_sec,
        subject=args.subject,
        qno_start=args.qno_start,
        qno_end=args.qno_end,
    )


if __name__ == "__main__":
    main()
