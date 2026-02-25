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
from datetime import datetime
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
COL_DISTRIBUTED = "답_배포"
COL_EXPLANATION = "해설"
COL_ANSWERED = "답변여부"

COL_BLACK_FAVORITE = "검정즐겨찾기"

LEGACY_REVIEW_COLUMNS = (
    "정답여부",
    "개정플래그",
    "검증상태",
    "검증메모",
    "검증일시",
)

DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass
class Question:
    year: int
    subject: str
    qno: int
    stem: str
    options: list[str]
    answer: str
    distributed: str


@dataclass
class ReviewResult:
    year: int
    subject: str
    qno: int
    decision: str
    final_answer: str
    topic: str
    explanation: str
    reason: str


def qi(name: str) -> str:
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def normalize_answer(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "모두" in text:
        return "1,2,3,4,5"
    ordered: list[str] = []
    for ch in text:
        if ch in "12345" and ch not in ordered:
            ordered.append(ch)
    return ",".join(ordered)


def load_api_key(direct_value: str, key_file: Path | None) -> str:
    if direct_value.strip():
        return direct_value.strip()
    if key_file and key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


def ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_QUESTIONS}")')}
    if COL_BLACK_FAVORITE not in columns:
        conn.execute(
            f'ALTER TABLE "{TABLE_QUESTIONS}" ADD COLUMN "{COL_BLACK_FAVORITE}" INTEGER NOT NULL DEFAULT 0'
        )
    if COL_ANSWERED not in columns:
        conn.execute(
            f'ALTER TABLE "{TABLE_QUESTIONS}" ADD COLUMN "{COL_ANSWERED}" INTEGER NOT NULL DEFAULT 0'
        )
    conn.commit()


def drop_legacy_review_columns(conn: sqlite3.Connection) -> int:
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_QUESTIONS}")')}
    dropped = 0
    for col in LEGACY_REVIEW_COLUMNS:
        if col not in columns:
            continue
        conn.execute(f'ALTER TABLE "{TABLE_QUESTIONS}" DROP COLUMN "{col}"')
        dropped += 1
    conn.commit()
    return dropped


def fetch_mismatches(conn: sqlite3.Connection, *, year: int, subject: str) -> list[Question]:
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
            "{COL_OPT_5}",
            "{COL_ANSWER}",
            "{COL_DISTRIBUTED}"
        FROM "{TABLE_QUESTIONS}"
        WHERE "{COL_YEAR}" = ?
          AND "{COL_SUBJECT}" = ?
          AND COALESCE(TRIM("{COL_DISTRIBUTED}"), '') <> ''
        ORDER BY "{COL_QNO}" ASC
    """
    rows = conn.execute(sql, (int(year), subject.strip())).fetchall()
    mismatches: list[Question] = []
    for row in rows:
        item = Question(
            year=int(row[0]),
            subject=str(row[1] or "").strip(),
            qno=int(row[2]),
            stem=str(row[3] or "").strip(),
            options=[
                str(row[4] or "").strip(),
                str(row[5] or "").strip(),
                str(row[6] or "").strip(),
                str(row[7] or "").strip(),
                str(row[8] or "").strip(),
            ],
            answer=normalize_answer(str(row[9] or "")),
            distributed=normalize_answer(str(row[10] or "")),
        )
        if item.answer != item.distributed:
            mismatches.append(item)
    return mismatches


def chunked(items: list[Question], size: int) -> list[list[Question]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_batch_prompt(batch: list[Question]) -> str:
    blocks: list[str] = []
    for q in batch:
        block = "\n".join(
            [
                f"[{q.year}년 {q.subject} {q.qno}번]",
                f"문제: {q.stem}",
                f"보기1: {q.options[0]}",
                f"보기2: {q.options[1]}",
                f"보기3: {q.options[2]}",
                f"보기4: {q.options[3]}",
                f"보기5: {q.options[4]}",
                f"기존_LLM_답: {q.answer or '(없음)'}",
                f"실제_배포답안(정답_기준): {q.distributed}",
            ]
        )
        blocks.append(block)

    instruction = """
너는 세무사 시험 검증 심사관이다.
아래 문제들을 각 문항마다 충분히 깊게(법조문/기준/논리 근거를 스스로 재검토) 검토하라.
중요: 원칙적으로 실제 정답 기준은 실제_배포답안이다.
단, 법령 또는 회계기준의 개정으로 현재 시점에서 실제_배포답안이 더 이상 타당하지 않다고 명확히 확신할 수 있는 경우에만 decision을 official_outdated로 판단하라.

출력은 반드시 JSON 배열만 반환하라. JSON 외 텍스트를 절대 쓰지 마라.
각 원소는 아래 키를 모두 포함하라:
- year: 정수
- subject: 문자열
- question_no: 정수
- decision: "official_valid" 또는 "official_outdated"
- final_answer: "1"~"5" 또는 "1,4" 형식
- topic: 문자열
- explanation: 문자열 (충분히 상세)
- reason: 문자열 (판단 근거 요약)

규칙:
1) decision=official_valid 인 경우 final_answer는 실제_배포답안과 반드시 같아야 한다.
2) decision=official_outdated 인 경우 final_answer는 현재 기준 정답으로 제시한다.
3) explanation은 보기별 판정 근거가 드러나도록 자세히 작성한다.
"""

    return instruction.strip() + "\n\n[검증 대상]\n" + "\n\n".join(blocks)


def call_gemini_text(
    *,
    api_key: str,
    model: str,
    api_url: str,
    prompt: str,
    timeout_sec: int,
) -> str:
    endpoint = api_url.format(model=model) if "{model}" in api_url else api_url
    sep = "&" if "?" in endpoint else "?"
    endpoint = f"{endpoint}{sep}key={urllib.parse.quote(api_key)}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
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

    payload_obj = json.loads(raw)
    for candidate in payload_obj.get("candidates") or []:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
        if texts:
            return "\n".join(texts).strip()
    raise RuntimeError(f"Gemini response has no text candidates: {raw}")


def parse_json_array_response(text: str) -> list[dict]:
    content = text.strip()
    if not content:
        raise ValueError("Empty response text")

    match = JSON_BLOCK_RE.search(content)
    if match:
        content = match.group(1).strip()

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"Response is not valid JSON array: {error}") from error
    if not isinstance(payload, list):
        raise ValueError("Response root is not a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def validate_and_bind_results(batch: list[Question], items: list[dict]) -> dict[int, ReviewResult]:
    expected = {(q.year, q.subject, q.qno): q for q in batch}
    bound: dict[int, ReviewResult] = {}
    for raw in items:
        try:
            year = int(raw.get("year"))
            subject = str(raw.get("subject") or "").strip()
            qno = int(raw.get("question_no"))
        except (TypeError, ValueError):
            continue
        key = (year, subject, qno)
        if key not in expected:
            continue
        decision = str(raw.get("decision") or "").strip().lower()
        if decision not in {"official_valid", "official_outdated"}:
            continue
        topic = str(raw.get("topic") or "").strip()
        explanation = str(raw.get("explanation") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        model_answer = normalize_answer(str(raw.get("final_answer") or ""))
        distributed = expected[key].distributed
        final_answer = distributed if decision == "official_valid" else (model_answer or distributed)
        if not final_answer:
            final_answer = distributed
        if decision == "official_valid":
            final_answer = distributed
        if not explanation:
            continue
        bound[qno] = ReviewResult(
            year=year,
            subject=subject,
            qno=qno,
            decision=decision,
            final_answer=final_answer,
            topic=topic,
            explanation=explanation,
            reason=reason,
        )
    return bound


def save_raw_response(output_dir: Path, *, year: int, subject: str, batch_no: int, text: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_subject = re.sub(r"[^\w가-힣]+", "_", subject.strip()) or "subject"
    path = output_dir / f"revalidate_raw_{year}_{safe_subject}_batch{batch_no}_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def apply_results(conn: sqlite3.Connection, results: list[ReviewResult]) -> dict[str, int]:
    update_sql = f"""
        UPDATE "{TABLE_QUESTIONS}"
        SET
            "{COL_ANSWER}" = ?,
            "{COL_EXPLANATION}" = ?,
            "{COL_ANSWERED}" = 1,
            "{COL_BLACK_FAVORITE}" = ?
        WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ? AND "{COL_QNO}" = ?
    """
    updated = 0
    outdated = 0
    valid = 0
    for item in results:
        body = item.explanation
        if item.topic:
            body = f"주제 : {item.topic}\n\n{body}"
        if item.reason:
            body = f"{body}\n\n[검증판단근거]\n{item.reason}"
        black = 1 if item.decision == "official_outdated" else 0
        if black:
            outdated += 1
        else:
            valid += 1
        cursor = conn.execute(
            update_sql,
            (
                item.final_answer,
                body.strip(),
                black,
                item.year,
                item.subject,
                item.qno,
            ),
        )
        if cursor.rowcount and cursor.rowcount > 0:
            updated += int(cursor.rowcount)
    conn.commit()
    return {"updated": updated, "official_outdated": outdated, "official_valid": valid}


def process_mismatches(
    *,
    db_path: Path,
    year: int,
    subject: str,
    api_key: str,
    model: str,
    api_url: str,
    batch_size: int,
    timeout_sec: int,
    sleep_sec: float,
    retries: int,
    raw_output_dir: Path,
) -> None:
    if not api_key:
        raise ValueError("Gemini API key is required")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    conn = sqlite3.connect(db_path)
    try:
        ensure_columns(conn)
        mismatches = fetch_mismatches(conn, year=year, subject=subject)
        if not mismatches:
            print("No mismatches found.")
            return
        print(f"Mismatch count: {len(mismatches)}")
        batches = chunked(mismatches, batch_size)
        all_results: list[ReviewResult] = []
        for index, batch in enumerate(batches, start=1):
            print(f"[Batch {index}/{len(batches)}] size={len(batch)}")
            prompt = build_batch_prompt(batch)
            last_error: Exception | None = None
            response_text = ""
            parsed_results: dict[int, ReviewResult] = {}
            for attempt in range(1, retries + 2):
                try:
                    response_text = call_gemini_text(
                        api_key=api_key,
                        model=model,
                        api_url=api_url,
                        prompt=prompt,
                        timeout_sec=timeout_sec,
                    )
                    save_path = save_raw_response(
                        raw_output_dir,
                        year=year,
                        subject=subject,
                        batch_no=index,
                        text=response_text,
                    )
                    print(f"[Batch {index}] raw saved: {save_path}")
                    payload = parse_json_array_response(response_text)
                    parsed_results = validate_and_bind_results(batch, payload)
                    if len(parsed_results) != len(batch):
                        missing = sorted(q.qno for q in batch if q.qno not in parsed_results)
                        raise RuntimeError(f"Incomplete parse. missing_qno={missing}")
                    break
                except Exception as error:  # noqa: BLE001
                    last_error = error
                    print(f"[Batch {index}] attempt {attempt} failed: {error}")
                    if attempt >= retries + 1:
                        raise
                    time.sleep(1.0)
            if last_error and not parsed_results:
                raise last_error
            ordered = [parsed_results[q.qno] for q in batch]
            all_results.extend(ordered)
            if sleep_sec > 0:
                time.sleep(sleep_sec)

        summary = apply_results(conn, all_results)
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-validate mismatched answers with Gemini in 5-question batches."
    )
    parser.add_argument("--db-path", default="data/questions.db")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--api-key-file", default="config/gemini_api_key.txt")
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--api-url", default=DEFAULT_GEMINI_URL)

    sub = parser.add_subparsers(dest="command", required=True)

    p_drop = sub.add_parser("drop-legacy-columns", help="Drop legacy review columns from 문제 table.")
    p_drop.set_defaults(cmd="drop")

    p_run = sub.add_parser("run", help="Run mismatch re-validation and update 답/해설.")
    p_run.add_argument("--year", type=int, required=True)
    p_run.add_argument("--subject", required=True)
    p_run.add_argument("--batch-size", type=int, default=5)
    p_run.add_argument("--timeout-sec", type=int, default=150)
    p_run.add_argument("--sleep-sec", type=float, default=1.0)
    p_run.add_argument("--retries", type=int, default=2)
    p_run.add_argument("--raw-output-dir", default="data/review/revalidate_raw")
    p_run.set_defaults(cmd="run")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    if args.cmd == "drop":
        conn = sqlite3.connect(db_path)
        try:
            ensure_columns(conn)
            dropped = drop_legacy_review_columns(conn)
        finally:
            conn.close()
        print(f"dropped={dropped}")
        return

    api_key = load_api_key(args.api_key, Path(args.api_key_file) if args.api_key_file else None)
    process_mismatches(
        db_path=db_path,
        year=int(args.year),
        subject=str(args.subject),
        api_key=api_key,
        model=args.model,
        api_url=args.api_url,
        batch_size=int(args.batch_size),
        timeout_sec=int(args.timeout_sec),
        sleep_sec=float(args.sleep_sec),
        retries=int(args.retries),
        raw_output_dir=Path(args.raw_output_dir),
    )


if __name__ == "__main__":
    main()
