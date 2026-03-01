from __future__ import annotations

import argparse
import base64
import io
import json
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image


def u(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


SUBJECT_FINANCE = u("\\uc7ac\\uc815\\ud559")
SUBJECT_TAX = u("\\uc138\\ubc95\\ud559\\uac1c\\ub860")
SUBJECT_ACCOUNTING = u("\\ud68c\\uacc4\\ud559\\uac1c\\ub860")
SUBJECT_COMMERCIAL = u("\\uc0c1\\ubc95")
SUBJECT_CIVIL = u("\\ubbfc\\ubc95")
SUBJECT_ADMIN = u("\\ud589\\uc815\\uc18c\\uc1a1\\ubc95")

SUBJECT_ORDER = [
    SUBJECT_FINANCE,
    SUBJECT_TAX,
    SUBJECT_ACCOUNTING,
    SUBJECT_COMMERCIAL,
    SUBJECT_CIVIL,
    SUBJECT_ADMIN,
]

EXPECTED_QUESTION_RANGES = {
    SUBJECT_FINANCE: range(1, 41),
    SUBJECT_ACCOUNTING: range(1, 41),
    SUBJECT_TAX: range(41, 81),
    SUBJECT_COMMERCIAL: range(41, 81),
    SUBJECT_CIVIL: range(41, 81),
    SUBJECT_ADMIN: range(41, 81),
}

CANONICAL_SUBJECT_MAP = {
    SUBJECT_FINANCE.replace(" ", ""): SUBJECT_FINANCE,
    SUBJECT_TAX.replace(" ", ""): SUBJECT_TAX,
    SUBJECT_ACCOUNTING.replace(" ", ""): SUBJECT_ACCOUNTING,
    SUBJECT_COMMERCIAL.replace(" ", ""): SUBJECT_COMMERCIAL,
    SUBJECT_CIVIL.replace(" ", ""): SUBJECT_CIVIL,
    SUBJECT_ADMIN.replace(" ", ""): SUBJECT_ADMIN,
}

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
class ExtractResult:
    year: int
    hwp_path: Path
    answer_map: dict[tuple[str, int], str]
    txt_path: Path
    updated_rows: int


def normalize_answer(raw: str) -> str:
    text = str(raw or "").strip().translate(CIRCLE_TO_DIGIT)
    text = text.replace(" ", "")
    if not text:
        return ""
    if u("\\ubaa8\\ub450") in text:
        return "1,2,3,4,5"

    ordered: list[str] = []
    for ch in text:
        if ch in "12345" and ch not in ordered:
            ordered.append(ch)
    return ",".join(ordered)


def normalize_subject(raw: str) -> str:
    compact = "".join(str(raw or "").split())
    return CANONICAL_SUBJECT_MAP.get(compact, "")


def find_year_dirs(data_root: Path, years: list[int] | None) -> list[tuple[int, Path]]:
    if years:
        found: list[tuple[int, Path]] = []
        for year in years:
            year_dir = data_root / str(year)
            if not year_dir.exists():
                raise FileNotFoundError(f"Year dir not found: {year_dir}")
            found.append((year, year_dir))
        return found

    found = []
    for child in sorted(data_root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if not child.name.isdigit():
            continue
        year = int(child.name)
        found.append((year, child))
    return found


def find_single_hwp(year_dir: Path) -> Path:
    hwps = sorted(year_dir.glob("*.hwp"))
    if len(hwps) != 1:
        raise FileNotFoundError(f"[{year_dir.name}] expected exactly 1 .hwp, got {len(hwps)}")
    return hwps[0]


def unpack_hwp(hwp_path: Path, out_dir: Path) -> list[Path]:
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["hwp5proc", "unpack", str(hwp_path), str(out_dir)], check=True, capture_output=True)
    img_dir = out_dir / "BinData"
    images = sorted(img_dir.glob("*.bmp"))
    if not images:
        raise RuntimeError(f"No bmp images in unpacked HWP: {hwp_path}")
    return images


def image_to_png_b64(image_path: Path, max_width: int = 2400) -> str:
    image = Image.open(image_path)
    if image.width > max_width:
        ratio = max_width / float(image.width)
        image = image.resize((int(image.width * ratio), int(image.height * ratio)))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_prompt_json() -> str:
    return (
        "The attached images contain the official final answer table for a Korean tax exam year. "
        "Return JSON only, no markdown, no explanation.\n"
        "Required schema:\n"
        "{\n"
        f'  "{SUBJECT_FINANCE}": {{"1":"",...,"40":""}},\n'
        f'  "{SUBJECT_TAX}": {{"41":"",...,"80":""}},\n'
        f'  "{SUBJECT_ACCOUNTING}": {{"1":"",...,"40":""}},\n'
        f'  "{SUBJECT_COMMERCIAL}": {{"41":"",...,"80":""}},\n'
        f'  "{SUBJECT_CIVIL}": {{"41":"",...,"80":""}},\n'
        f'  "{SUBJECT_ADMIN}": {{"41":"",...,"80":""}}\n'
        "}\n"
        'Each value must be one of "1","2","3","4","5" or multi-answer like "1,4".'
    )


def call_gemini_json(
    *,
    api_key: str,
    model: str,
    images: Iterable[Path],
    timeout_sec: int = 240,
) -> str:
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={urllib.parse.quote(api_key)}"
    )

    parts: list[dict] = [{"text": build_prompt_json()}]
    for image_path in images:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "image/png",
                    "data": image_to_png_b64(image_path),
                }
            }
        )

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini HTTP {error.code}: {details}") from error

    obj = json.loads(raw)
    texts: list[str] = []
    for candidate in obj.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
    if not texts:
        raise RuntimeError("Gemini returned no text.")
    return "\n".join(texts).strip()


def parse_answer_json_text(text: str) -> dict[tuple[str, int], str]:
    data = json.loads(text)
    out: dict[tuple[str, int], str] = {}

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            subject = normalize_subject(item.get("subject", ""))
            if not subject:
                continue
            answers = item.get("answers") or []
            if not isinstance(answers, list):
                continue
            for entry in answers:
                if not isinstance(entry, dict):
                    continue
                try:
                    qno = int(entry.get("question"))
                except (TypeError, ValueError):
                    continue
                ans = normalize_answer(entry.get("answer", ""))
                if ans:
                    out[(subject, qno)] = ans
        return out

    if isinstance(data, dict):
        for raw_subject, answer_obj in data.items():
            subject = normalize_subject(raw_subject)
            if not subject or not isinstance(answer_obj, dict):
                continue
            for raw_qno, raw_answer in answer_obj.items():
                try:
                    qno = int(raw_qno)
                except (TypeError, ValueError):
                    continue
                ans = normalize_answer(raw_answer)
                if ans:
                    out[(subject, qno)] = ans
        return out

    raise ValueError(f"Unexpected JSON root type: {type(data)}")


def merge_attempts(attempt_maps: list[dict[tuple[str, int], str]]) -> dict[tuple[str, int], str]:
    merged: dict[tuple[str, int], str] = {}
    all_keys: set[tuple[str, int]] = set()
    for mapping in attempt_maps:
        all_keys.update(mapping.keys())

    for key in sorted(all_keys, key=lambda item: (item[0], item[1])):
        votes = [mapping[key] for mapping in attempt_maps if key in mapping and mapping[key]]
        if not votes:
            continue
        counter = Counter(votes)
        best_answer = counter.most_common(1)[0][0]
        merged[key] = best_answer
    return merged


def validate_answer_map(answer_map: dict[tuple[str, int], str]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    invalid: list[str] = []

    for subject in SUBJECT_ORDER:
        for qno in EXPECTED_QUESTION_RANGES[subject]:
            key = (subject, qno)
            answer = answer_map.get(key, "")
            if not answer:
                missing.append(f"{subject} {qno}")
                continue
            for token in answer.split(","):
                if token not in {"1", "2", "3", "4", "5"}:
                    invalid.append(f"{subject} {qno}: {answer}")
                    break
    return missing, invalid


def build_answer_txt_content(answer_map: dict[tuple[str, int], str], year: int) -> str:
    lines: list[str] = []
    title = u("\\uc81c{year}\\ud68c").format(year=year - 1963)
    lines.append(f"{year}년 {title} 세무사 1차 국가자격시험 과목별 최종 정답")
    lines.append("")
    lines.append("### **[1교시]**")
    lines.append("")

    for subject in [SUBJECT_FINANCE, SUBJECT_TAX]:
        lines.append(f"**{subject}**")
        lines.append("")
        qnos = list(EXPECTED_QUESTION_RANGES[subject])
        for i in range(0, len(qnos), 5):
            chunk = qnos[i : i + 5]
            pairs = [f"**{qno}**:{answer_map[(subject, qno)]}" for qno in chunk]
            lines.append("* " + ", ".join(pairs))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("### **[2교시]**")
    lines.append("")

    for subject in [SUBJECT_ACCOUNTING, SUBJECT_COMMERCIAL, SUBJECT_CIVIL, SUBJECT_ADMIN]:
        lines.append(f"**{subject}**")
        lines.append("")
        qnos = list(EXPECTED_QUESTION_RANGES[subject])
        for i in range(0, len(qnos), 5):
            chunk = qnos[i : i + 5]
            pairs = [f"**{qno}**:{answer_map[(subject, qno)]}" for qno in chunk]
            lines.append("* " + ", ".join(pairs))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def update_db_distributed_answers(
    conn: sqlite3.Connection,
    *,
    year: int,
    answer_map: dict[tuple[str, int], str],
) -> int:
    table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY rowid").fetchone()[0]
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info(\"{table}\")")]
    col_year, col_subject, col_qno, col_distributed = cols[1], cols[2], cols[3], cols[11]

    sql = (
        f'UPDATE "{table}" SET "{col_distributed}" = ? '
        f'WHERE "{col_year}" = ? AND "{col_subject}" = ? AND "{col_qno}" = ?'
    )
    updated = 0
    for (subject, qno), answer in answer_map.items():
        cur = conn.execute(sql, (answer, year, subject, qno))
        updated += int(cur.rowcount or 0)
    conn.commit()
    return updated


def load_api_key(direct: str, key_file: Path | None) -> str:
    if direct.strip():
        return direct.strip()
    if key_file and key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


def run_for_year(
    *,
    year: int,
    year_dir: Path,
    api_key: str,
    model: str,
    attempts: int,
    db_conn: sqlite3.Connection,
) -> ExtractResult:
    hwp_path = find_single_hwp(year_dir)
    unpack_dir = year_dir / "_hwp_unpack_published_answers"
    images = unpack_hwp(hwp_path, unpack_dir)

    attempt_maps: list[dict[tuple[str, int], str]] = []
    for idx in range(attempts):
        text = call_gemini_json(api_key=api_key, model=model, images=images)
        parsed = parse_answer_json_text(text)
        attempt_maps.append(parsed)
        missing, invalid = validate_answer_map(parsed)
        print(
            f"[{year}] attempt {idx + 1}/{attempts}: parsed={len(parsed)}, "
            f"missing={len(missing)}, invalid={len(invalid)}"
        )
        if not missing and not invalid:
            # Good enough: still keep this attempt and stop early.
            break

    merged = merge_attempts(attempt_maps)
    missing, invalid = validate_answer_map(merged)
    if missing or invalid:
        raise RuntimeError(
            f"[{year}] extraction incomplete after {len(attempt_maps)} attempts: "
            f"missing={len(missing)}, invalid={len(invalid)}"
        )

    txt_content = build_answer_txt_content(merged, year)
    txt_path = year_dir / u("\\uc2e4\\uc81c\\uc815\\ub2f5.txt")
    txt_path.write_text(txt_content, encoding="utf-8")

    updated_rows = update_db_distributed_answers(db_conn, year=year, answer_map=merged)

    shutil.rmtree(unpack_dir, ignore_errors=True)
    return ExtractResult(
        year=year,
        hwp_path=hwp_path,
        answer_map=merged,
        txt_path=txt_path,
        updated_rows=updated_rows,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract official distributed answers from year HWP files and update 답_배포."
    )
    parser.add_argument("--data-root", default="data", help="Root directory containing year folders.")
    parser.add_argument("--db-path", default="data/questions.db", help="SQLite DB path.")
    parser.add_argument("--years", nargs="*", type=int, default=None, help="Target years. Default: all year dirs.")
    parser.add_argument("--api-key", default="", help="Gemini API key.")
    parser.add_argument(
        "--api-key-file",
        default="config/gemini_api_key.txt",
        help="Gemini API key file (used when --api-key is empty).",
    )
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model.")
    parser.add_argument("--attempts", type=int, default=2, help="Extraction attempts per year for majority voting.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_root = Path(args.data_root)
    db_path = Path(args.db_path)
    api_key = load_api_key(args.api_key, Path(args.api_key_file) if args.api_key_file else None)
    if not api_key:
        raise RuntimeError("Gemini API key is required (--api-key or --api-key-file).")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    year_dirs = find_year_dirs(data_root, args.years)
    if not year_dirs:
        raise RuntimeError(f"No year dirs found under: {data_root}")

    conn = sqlite3.connect(db_path)
    try:
        results: list[ExtractResult] = []
        for year, year_dir in year_dirs:
            if not list(year_dir.glob("*.hwp")):
                print(f"[{year}] skip: no .hwp file")
                continue
            result = run_for_year(
                year=year,
                year_dir=year_dir,
                api_key=api_key,
                model=args.model,
                attempts=max(1, int(args.attempts)),
                db_conn=conn,
            )
            results.append(result)
            print(
                f"[{year}] done: hwp={result.hwp_path.name}, txt={result.txt_path.name}, "
                f"answers={len(result.answer_map)}, updated_rows={result.updated_rows}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()

