from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from html import escape
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR.parent / "data" / "questions.db"

SUBJECTS = (
    "재정학",
    "세법학개론",
    "회계학개론",
    "상법",
    "민법",
    "행정소송법",
)
IMPORTANCE_LEVELS = ("red", "yellow", "green", "gray")
DEFAULT_IMPORTANCE = "green"
DEFAULT_USER_ID = "guest"

TABLE_QUESTIONS = "문제"
TABLE_OX = "문제_OX"
TABLE_WRONG_NOTE = "오답노트"
TABLE_APP_META = "app_meta"

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
COL_RENDER = "렌더_마크업"
COL_YEAR = "출제연도"
COL_SUBJECT = "과목"

COL_OX_QNO = "문제번호"
COL_OX_QUESTION = "문제"
COL_OX_ANSWER = "답"
COL_OX_EXPLANATION = "해설"

COL_NOTE_IMPORTANCE = "중요도"
COL_NOTE_COMMENT = "코멘트"
COL_NOTE_UPDATED = "수정일시"
COL_NOTE_USER = "user_id"
COL_META_KEY = "meta_key"
COL_META_VALUE = "meta_value"
FIRST_RUN_INIT_KEY = "first_run_user_note_reset_done"

PUA_TRANSLATION = str.maketrans(
    {
        "\ue000": "A",
        "\ue001": "B",
        "\ue002": "C",
        "\ue003": "D",
        "\ue00c": "M",
        "\ue00f": "P",
        "\ue010": "Q",
        "\ue012": "S",
        "\ue014": "U",
        "\ue016": "W",
        "\ue017": "X",
        "\ue034": "1",
        "\ue035": "2",
        "\ue036": "3",
        "\ue037": "4",
        "\ue038": "5",
        "\ue039": "9",
        "\ue03b": "8",
        "\ue03d": "0",
        "\ue044": "x",
        "\ue045": "",
        "\ue046": "-",
        "\ue047": "=",
        "\ue048": "+",
        "\ue04b": "{",
        "\ue04c": "}",
        "\ue052": ",",
        "\ue056": "Σ",
        "\ue05c": "√",
        "\ue06d": "",
        "\ue0ed": "i",
    }
)
PUA_RE = re.compile(r"[\ue000-\uf8ff]")
MATH_LINE_RE = re.compile(r"^[A-Za-z0-9\s=+\-*/(),.{}\[\]_\\^%Σ√>|:]+$")
OX_QUESTION_PREFIX_RE = re.compile(r"^\s*(?:문제\s*)?(?:\d+|[①-⑳])\s*[\.\)\]:：\-]\s*")


def normalize_question_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.translate(PUA_TRANSLATION)
    normalized = PUA_RE.sub("", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return normalized.strip()


def normalize_math_tex(text: str) -> str:
    tex = text
    tex = re.sub(r"√\s*([A-Za-z0-9_]+)", r"\\sqrt{\1}", tex)
    tex = tex.replace("Σ", r"\sum")
    return tex


def render_line_html(text: str) -> str:
    stripped = text.strip()
    if stripped:
        has_math_token = any(token in stripped for token in ("=", "_", "√", "Σ", "\\"))
        has_korean = bool(re.search(r"[가-힣]", stripped))
        if has_math_token and not has_korean and MATH_LINE_RE.match(stripped):
            math_text = normalize_math_tex(stripped)
            return f'<div class="rich-line rich-math">\\({escape(math_text)}\\)</div>'
    return f'<div class="rich-line">{escape(text)}</div>'


def render_plain_text_html(text: str) -> str:
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ""
    html_lines = "".join(render_line_html(line) for line in lines)
    return f'<div class="rich-content">{html_lines}</div>'


def normalize_ox_question_text(text: str) -> str:
    normalized = normalize_question_text(text)
    if not normalized:
        return ""
    lines = normalized.split("\n")
    lines[0] = OX_QUESTION_PREFIX_RE.sub("", lines[0]).strip()
    return "\n".join(lines).strip()


def parse_render_markup(raw: str) -> dict:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def repair_known_artifacts(
    *,
    year: int,
    subject: str,
    question_no: int,
    stem: str,
    options: list[str],
) -> tuple[str, list[str]]:
    if year == 2025 and subject == "재정학" and question_no == 5:
        options[0] = re.sub(r"\n\s*3\s*$", "", options[0]).strip()
        options[1] = re.sub(
            r"비효율성계수는\s*이다\.\s*4\s*$",
            "비효율성계수는 3/4이다.",
            options[1],
            flags=re.DOTALL,
        )
    return stem, options


def normalize_user_id(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return DEFAULT_USER_ID
    if len(normalized) > 64:
        return normalized[:64]
    return normalized


def ensure_wrong_note_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_WRONG_NOTE}")')}
    has_user_col = COL_NOTE_USER in columns

    unique_ok = False
    for index in conn.execute(f'PRAGMA index_list("{TABLE_WRONG_NOTE}")').fetchall():
        if int(index[2]) != 1:
            continue
        index_name = str(index[1])
        index_columns = [row[2] for row in conn.execute(f'PRAGMA index_info("{index_name}")').fetchall()]
        if index_columns == [COL_NOTE_USER, COL_YEAR, COL_SUBJECT, COL_QNO]:
            unique_ok = True
            break

    if has_user_col and unique_ok:
        return

    legacy_table = f"{TABLE_WRONG_NOTE}_legacy"
    conn.execute(f'DROP TABLE IF EXISTS "{legacy_table}"')
    conn.execute(f'ALTER TABLE "{TABLE_WRONG_NOTE}" RENAME TO "{legacy_table}"')
    conn.execute(
        f"""
        CREATE TABLE "{TABLE_WRONG_NOTE}" (
            오답노트id INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_NOTE_USER}" TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_QNO}" INTEGER NOT NULL,
            "{COL_NOTE_IMPORTANCE}" TEXT NOT NULL DEFAULT '{DEFAULT_IMPORTANCE}',
            "{COL_NOTE_COMMENT}" TEXT NOT NULL DEFAULT '',
            "{COL_NOTE_UPDATED}" TEXT NOT NULL,
            UNIQUE ("{COL_NOTE_USER}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
        )
        """
    )

    legacy_columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{legacy_table}")')}
    if COL_NOTE_USER in legacy_columns:
        conn.execute(
            f"""
            INSERT INTO "{TABLE_WRONG_NOTE}"
            ("{COL_NOTE_USER}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
            SELECT
                COALESCE(NULLIF(TRIM("{COL_NOTE_USER}"), ''), ?),
                "{COL_YEAR}",
                "{COL_SUBJECT}",
                "{COL_QNO}",
                "{COL_NOTE_IMPORTANCE}",
                "{COL_NOTE_COMMENT}",
                "{COL_NOTE_UPDATED}"
            FROM "{legacy_table}"
            """,
            (DEFAULT_USER_ID,),
        )
    else:
        conn.execute(
            f"""
            INSERT INTO "{TABLE_WRONG_NOTE}"
            ("{COL_NOTE_USER}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
            SELECT
                ?,
                "{COL_YEAR}",
                "{COL_SUBJECT}",
                "{COL_QNO}",
                "{COL_NOTE_IMPORTANCE}",
                "{COL_NOTE_COMMENT}",
                "{COL_NOTE_UPDATED}"
            FROM "{legacy_table}"
            """,
            (DEFAULT_USER_ID,),
        )
    conn.execute(f'DROP TABLE "{legacy_table}"')


def ensure_app_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_OX}" (
            ox문제id INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_OX_QNO}" INTEGER NOT NULL,
            "{COL_OX_QUESTION}" TEXT NOT NULL,
            "{COL_OX_ANSWER}" TEXT NOT NULL,
            "{COL_OX_EXPLANATION}" TEXT NOT NULL,
            UNIQUE ("{COL_YEAR}", "{COL_SUBJECT}", "{COL_OX_QNO}")
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_WRONG_NOTE}" (
            오답노트id INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_NOTE_USER}" TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_QNO}" INTEGER NOT NULL,
            "{COL_NOTE_IMPORTANCE}" TEXT NOT NULL DEFAULT '{DEFAULT_IMPORTANCE}',
            "{COL_NOTE_COMMENT}" TEXT NOT NULL DEFAULT '',
            "{COL_NOTE_UPDATED}" TEXT NOT NULL,
            UNIQUE ("{COL_NOTE_USER}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
        )
        """
    )
    ensure_wrong_note_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_APP_META}" (
            "{COL_META_KEY}" TEXT PRIMARY KEY,
            "{COL_META_VALUE}" TEXT NOT NULL
        )
        """
    )
    initialized = conn.execute(
        f'SELECT 1 FROM "{TABLE_APP_META}" WHERE "{COL_META_KEY}" = ? LIMIT 1',
        (FIRST_RUN_INIT_KEY,),
    ).fetchone()
    if initialized is None:
        # First-launch reset for user-authored note data.
        conn.execute(f'DELETE FROM "{TABLE_WRONG_NOTE}"')
        conn.execute(
            f'INSERT INTO "{TABLE_APP_META}" ("{COL_META_KEY}", "{COL_META_VALUE}") VALUES (?, ?)',
            (FIRST_RUN_INIT_KEY, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    placeholders = ", ".join("?" for _ in IMPORTANCE_LEVELS)
    conn.execute(
        f"""
        UPDATE "{TABLE_WRONG_NOTE}"
        SET "{COL_NOTE_IMPORTANCE}" = ?
        WHERE TRIM(COALESCE("{COL_NOTE_IMPORTANCE}", '')) = ''
           OR LOWER(TRIM("{COL_NOTE_IMPORTANCE}")) NOT IN ({placeholders})
        """,
        (DEFAULT_IMPORTANCE, *IMPORTANCE_LEVELS),
    )
    conn.commit()


def make_json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def fetch_questions(year: int, subject: str) -> list[dict]:
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_QUESTIONS}")')}
        has_render_markup = COL_RENDER in columns
        select_cols = [
            f'"{COL_QNO}"',
            f'"{COL_STEM}"',
            f'"{COL_OPT_1}"',
            f'"{COL_OPT_2}"',
            f'"{COL_OPT_3}"',
            f'"{COL_OPT_4}"',
            f'"{COL_OPT_5}"',
            f'"{COL_ANSWER}"',
            f'"{COL_DISTRIBUTED}"',
            f'"{COL_EXPLANATION}"',
        ]
        if has_render_markup:
            select_cols.append(f'"{COL_RENDER}"')
        sql = f"""
            SELECT {", ".join(select_cols)}
            FROM "{TABLE_QUESTIONS}"
            WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?
            ORDER BY "{COL_QNO}" ASC
        """
        rows = conn.execute(sql, (year, subject)).fetchall()
    finally:
        conn.close()

    questions: list[dict] = []
    for row in rows:
        if len(row) == 11:
            original_no, stem, o1, o2, o3, o4, o5, answer, distributed, explanation, render_markup = row
        else:
            original_no, stem, o1, o2, o3, o4, o5, answer, distributed, explanation = row
            render_markup = ""
        normalized_stem = normalize_question_text(stem or "")
        normalized_options = [
            normalize_question_text(o1 or ""),
            normalize_question_text(o2 or ""),
            normalize_question_text(o3 or ""),
            normalize_question_text(o4 or ""),
            normalize_question_text(o5 or ""),
        ]
        normalized_stem, normalized_options = repair_known_artifacts(
            year=year,
            subject=subject,
            question_no=int(original_no),
            stem=normalized_stem,
            options=normalized_options,
        )
        render_payload = parse_render_markup(render_markup)
        stem_html = str(render_payload.get("stem_html") or "").strip() or render_plain_text_html(normalized_stem)
        raw_options_html = render_payload.get("options_html")
        options_html: list[str] = []
        for index in range(5):
            candidate = ""
            if isinstance(raw_options_html, list) and index < len(raw_options_html):
                value = raw_options_html[index]
                if isinstance(value, str):
                    candidate = value.strip()
            options_html.append(candidate if candidate else render_plain_text_html(normalized_options[index]))
        questions.append(
            {
                "original_no": int(original_no),
                "stem": normalized_stem,
                "stem_html": stem_html,
                "options": normalized_options,
                "options_html": options_html,
                "answer": normalize_question_text(answer or ""),
                "distributed_answer": normalize_question_text(distributed or ""),
                "explanation": normalize_question_text(explanation or ""),
            }
        )
    return questions


def fetch_ox_questions(year: int, subject: str) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        sql = f"""
            SELECT "{COL_OX_QNO}", "{COL_OX_QUESTION}", "{COL_OX_ANSWER}", "{COL_OX_EXPLANATION}"
            FROM "{TABLE_OX}"
            WHERE "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?
            ORDER BY "{COL_OX_QNO}" ASC
        """
        rows = conn.execute(sql, (year, subject)).fetchall()
    finally:
        conn.close()
    return [
        {
            "original_no": int(qno),
            "question": normalize_ox_question_text(question or ""),
            "answer": normalize_question_text(answer or ""),
            "explanation": normalize_question_text(explanation or ""),
        }
        for qno, question, answer, explanation in rows
    ]


def fetch_wrong_note_map(year: int, subject: str, user_id: str) -> dict[str, dict]:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        sql = f"""
            SELECT "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}"
            FROM "{TABLE_WRONG_NOTE}"
            WHERE "{COL_NOTE_USER}" = ? AND "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?
        """
        rows = conn.execute(sql, (normalize_user_id(user_id), year, subject)).fetchall()
    finally:
        conn.close()
    result: dict[str, dict] = {}
    for qno, importance, comment, updated_at in rows:
        normalized_importance = (importance or "").strip().lower()
        if normalized_importance not in IMPORTANCE_LEVELS:
            normalized_importance = DEFAULT_IMPORTANCE
        result[str(int(qno))] = {
            "importance": normalized_importance,
            "comment": comment or "",
            "updated_at": updated_at or "",
        }
    return result


def fetch_wrong_notes(
    *,
    user_id: str,
    subject: str = "",
    importance: str = "",
    comment: str = "",
) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        filters: list[str] = []
        params: list[object] = []
        filters.append(f'n."{COL_NOTE_USER}" = ?')
        params.append(normalize_user_id(user_id))
        if subject:
            filters.append(f'n."{COL_SUBJECT}" = ?')
            params.append(subject)
        if importance:
            filters.append(
                f'COALESCE(NULLIF(n."{COL_NOTE_IMPORTANCE}", \'\'), \'{DEFAULT_IMPORTANCE}\') = ?'
            )
            params.append(importance)
        if comment:
            filters.append(f'n."{COL_NOTE_COMMENT}" LIKE ?')
            params.append(f"%{comment}%")
        where_clause = f'WHERE {" AND ".join(filters)}' if filters else ""
        sql = f"""
            SELECT
                n."{COL_YEAR}",
                n."{COL_SUBJECT}",
                n."{COL_QNO}",
                n."{COL_NOTE_IMPORTANCE}",
                n."{COL_NOTE_COMMENT}",
                n."{COL_NOTE_UPDATED}",
                q."{COL_STEM}"
            FROM "{TABLE_WRONG_NOTE}" n
            LEFT JOIN "{TABLE_QUESTIONS}" q
              ON q."{COL_YEAR}" = n."{COL_YEAR}"
             AND q."{COL_SUBJECT}" = n."{COL_SUBJECT}"
             AND q."{COL_QNO}" = n."{COL_QNO}"
            {where_clause}
            ORDER BY n."{COL_NOTE_UPDATED}" DESC, n."{COL_YEAR}" DESC, n."{COL_SUBJECT}" ASC, n."{COL_QNO}" ASC
        """
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    results: list[dict] = []
    for year, note_subject, question_no, note_importance, note_comment, updated_at, stem in rows:
        normalized_importance = (note_importance or "").strip().lower()
        if normalized_importance not in IMPORTANCE_LEVELS:
            normalized_importance = DEFAULT_IMPORTANCE
        preview = normalize_question_text(stem or "")
        if len(preview) > 140:
            preview = f"{preview[:140]}..."
        results.append(
            {
                "year": int(year),
                "subject": note_subject,
                "question_no": int(question_no),
                "importance": normalized_importance,
                "comment": note_comment or "",
                "updated_at": updated_at or "",
                "question_preview": preview,
            }
        )
    return results


def upsert_wrong_note(
    *,
    user_id: str,
    year: int,
    subject: str,
    question_no: int,
    importance: str,
    comment: str,
) -> None:
    normalized_user_id = normalize_user_id(user_id)
    raw_importance = (importance or "").strip().lower()
    normalized_importance = raw_importance if raw_importance in IMPORTANCE_LEVELS else DEFAULT_IMPORTANCE
    normalized_comment = normalize_question_text(comment or "")
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        if not raw_importance and not normalized_comment:
            conn.execute(
                f"""
                DELETE FROM "{TABLE_WRONG_NOTE}"
                WHERE "{COL_NOTE_USER}" = ? AND "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ? AND "{COL_QNO}" = ?
                """,
                (normalized_user_id, year, subject, question_no),
            )
        else:
            conn.execute(
                f"""
                INSERT INTO "{TABLE_WRONG_NOTE}"
                ("{COL_NOTE_USER}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT("{COL_NOTE_USER}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
                DO UPDATE SET
                    "{COL_NOTE_IMPORTANCE}" = excluded."{COL_NOTE_IMPORTANCE}",
                    "{COL_NOTE_COMMENT}" = excluded."{COL_NOTE_COMMENT}",
                    "{COL_NOTE_UPDATED}" = excluded."{COL_NOTE_UPDATED}"
                """,
                (
                    normalized_user_id,
                    year,
                    subject,
                    question_no,
                    normalized_importance,
                    normalized_comment,
                    updated_at,
                ),
            )
        conn.commit()
    finally:
        conn.close()


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/questions":
            self.handle_questions_api(parsed.query)
            return
        if parsed.path == "/api/ox/questions":
            self.handle_ox_questions_api(parsed.query)
            return
        if parsed.path == "/api/wrong-notes":
            self.handle_wrong_notes_api(parsed.query)
            return
        if parsed.path == "/api/wrong-notes/map":
            self.handle_wrong_notes_map_api(parsed.query)
            return
        if parsed.path == "/api/health":
            make_json_response(self, {"ok": True})
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/wrong-notes":
            self.handle_wrong_note_upsert_api()
            return
        make_json_response(self, {"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def handle_questions_api(self, query: str) -> None:
        params = parse_qs(query)
        year_text = (params.get("year") or [""])[0]
        subject = (params.get("subject") or [""])[0]
        try:
            year = int(year_text)
        except ValueError:
            make_json_response(self, {"error": "invalid year"}, status=HTTPStatus.BAD_REQUEST)
            return
        if subject not in SUBJECTS:
            make_json_response(self, {"error": "invalid subject"}, status=HTTPStatus.BAD_REQUEST)
            return
        questions = fetch_questions(year, subject)
        make_json_response(self, {"year": year, "subject": subject, "count": len(questions), "questions": questions})

    def handle_ox_questions_api(self, query: str) -> None:
        params = parse_qs(query)
        year_text = (params.get("year") or ["2025"])[0]
        subject = (params.get("subject") or ["재정학"])[0]
        try:
            year = int(year_text)
        except ValueError:
            make_json_response(self, {"error": "invalid year"}, status=HTTPStatus.BAD_REQUEST)
            return
        questions = fetch_ox_questions(year, subject)
        make_json_response(self, {"year": year, "subject": subject, "count": len(questions), "questions": questions})

    def handle_wrong_notes_api(self, query: str) -> None:
        params = parse_qs(query)
        user_id = normalize_user_id((params.get("user_id") or [""])[0])
        subject = (params.get("subject") or [""])[0]
        importance = (params.get("importance") or [""])[0].lower()
        comment = (params.get("comment") or [""])[0]
        if subject and subject not in SUBJECTS:
            make_json_response(self, {"error": "invalid subject"}, status=HTTPStatus.BAD_REQUEST)
            return
        if importance and importance not in IMPORTANCE_LEVELS:
            make_json_response(self, {"error": "invalid importance"}, status=HTTPStatus.BAD_REQUEST)
            return
        notes = fetch_wrong_notes(user_id=user_id, subject=subject, importance=importance, comment=comment)
        make_json_response(self, {"user_id": user_id, "count": len(notes), "items": notes})

    def handle_wrong_notes_map_api(self, query: str) -> None:
        params = parse_qs(query)
        user_id = normalize_user_id((params.get("user_id") or [""])[0])
        year_text = (params.get("year") or [""])[0]
        subject = (params.get("subject") or [""])[0]
        try:
            year = int(year_text)
        except ValueError:
            make_json_response(self, {"error": "invalid year"}, status=HTTPStatus.BAD_REQUEST)
            return
        if subject not in SUBJECTS:
            make_json_response(self, {"error": "invalid subject"}, status=HTTPStatus.BAD_REQUEST)
            return
        note_map = fetch_wrong_note_map(year, subject, user_id)
        make_json_response(self, {"user_id": user_id, "year": year, "subject": subject, "items": note_map})

    def handle_wrong_note_upsert_api(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            make_json_response(self, {"error": "invalid content length"}, status=HTTPStatus.BAD_REQUEST)
            return
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            make_json_response(self, {"error": "invalid json"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            year = int(payload.get("year"))
            question_no = int(payload.get("question_no"))
        except (TypeError, ValueError):
            make_json_response(self, {"error": "invalid year/question_no"}, status=HTTPStatus.BAD_REQUEST)
            return
        subject = str(payload.get("subject") or "")
        if subject not in SUBJECTS:
            make_json_response(self, {"error": "invalid subject"}, status=HTTPStatus.BAD_REQUEST)
            return
        user_id = normalize_user_id(str(payload.get("user_id") or ""))
        importance = str(payload.get("importance") or "")
        comment = str(payload.get("comment") or "")
        upsert_wrong_note(
            user_id=user_id,
            year=year,
            subject=subject,
            question_no=question_no,
            importance=importance,
            comment=comment,
        )
        make_json_response(self, {"ok": True, "user_id": user_id})


def main() -> None:
    parser = argparse.ArgumentParser(description="Tax exam local web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    with sqlite3.connect(DB_PATH) as conn:
        ensure_app_tables(conn)

    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
