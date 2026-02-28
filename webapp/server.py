from __future__ import annotations

import argparse
import json
import os
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
    "국세기본법",
    "국세징수법",
    "소득세법",
    "법인세법",
    "부가가치세법",
    "조세범처벌법",
)
IMPORTANCE_LEVELS = ("red", "yellow", "green", "gray")
DEFAULT_IMPORTANCE = ""
DEFAULT_USER_ID = "guest"
NOTICE_ADMIN_KEY = os.getenv("NOTICE_ADMIN_KEY", "").strip()
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "rian4u@naver.com").strip() or "rian4u@naver.com"

TABLE_QUESTIONS = "문제"
TABLE_OX = "OX"
TABLE_WRONG_NOTE = "오답노트"
TABLE_APP_META = "app_meta"
TABLE_QA_POST = "qa_posts"
TABLE_QA_ANSWER = "qa_answers"
TABLE_NOTICE = "공지게시판"

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
COL_NOTE_SOURCE = "source"
COL_META_KEY = "meta_key"
COL_META_VALUE = "meta_value"
FIRST_RUN_INIT_KEY = "first_run_user_note_reset_done"
NOTE_SOURCE_QUESTION = "question"
NOTE_SOURCE_OX = "ox"

COL_NOTICE_ID = "notice_id"
COL_NOTICE_TITLE = "title"
COL_NOTICE_BODY = "body"
COL_NOTICE_AUTHOR = "author"
COL_NOTICE_PUBLISHED = "is_published"
COL_NOTICE_CREATED = "created_at"
COL_NOTICE_UPDATED = "updated_at"
COL_QA_POST_ID = "id"
COL_QA_ANSWER_ID = "id"

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
    has_source_col = COL_NOTE_SOURCE in columns

    unique_ok = False
    for index in conn.execute(f'PRAGMA index_list("{TABLE_WRONG_NOTE}")').fetchall():
        if int(index[2]) != 1:
            continue
        index_name = str(index[1])
        index_columns = [row[2] for row in conn.execute(f'PRAGMA index_info("{index_name}")').fetchall()]
        if index_columns == [COL_NOTE_USER, COL_NOTE_SOURCE, COL_YEAR, COL_SUBJECT, COL_QNO]:
            unique_ok = True
            break

    if has_user_col and has_source_col and unique_ok:
        return

    legacy_table = f"{TABLE_WRONG_NOTE}_legacy"
    conn.execute(f'DROP TABLE IF EXISTS "{legacy_table}"')
    conn.execute(f'ALTER TABLE "{TABLE_WRONG_NOTE}" RENAME TO "{legacy_table}"')
    conn.execute(
        f"""
        CREATE TABLE "{TABLE_WRONG_NOTE}" (
            오답노트id INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_NOTE_USER}" TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}',
            "{COL_NOTE_SOURCE}" TEXT NOT NULL DEFAULT '{NOTE_SOURCE_QUESTION}',
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_QNO}" INTEGER NOT NULL,
            "{COL_NOTE_IMPORTANCE}" TEXT NOT NULL DEFAULT '{DEFAULT_IMPORTANCE}',
            "{COL_NOTE_COMMENT}" TEXT NOT NULL DEFAULT '',
            "{COL_NOTE_UPDATED}" TEXT NOT NULL,
            UNIQUE ("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
        )
        """
    )

    legacy_columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{legacy_table}")')}
    if COL_NOTE_USER in legacy_columns and COL_NOTE_SOURCE in legacy_columns:
        conn.execute(
            f"""
            INSERT INTO "{TABLE_WRONG_NOTE}"
            ("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
            SELECT
                COALESCE(NULLIF(TRIM("{COL_NOTE_USER}"), ''), ?),
                COALESCE(NULLIF(TRIM("{COL_NOTE_SOURCE}"), ''), ?),
                "{COL_YEAR}",
                "{COL_SUBJECT}",
                "{COL_QNO}",
                "{COL_NOTE_IMPORTANCE}",
                "{COL_NOTE_COMMENT}",
                "{COL_NOTE_UPDATED}"
            FROM "{legacy_table}"
            """,
            (DEFAULT_USER_ID, NOTE_SOURCE_QUESTION),
        )
    elif COL_NOTE_USER in legacy_columns:
        conn.execute(
            f"""
            INSERT INTO "{TABLE_WRONG_NOTE}"
            ("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
            SELECT
                COALESCE(NULLIF(TRIM("{COL_NOTE_USER}"), ''), ?),
                ?,
                "{COL_YEAR}",
                "{COL_SUBJECT}",
                "{COL_QNO}",
                "{COL_NOTE_IMPORTANCE}",
                "{COL_NOTE_COMMENT}",
                "{COL_NOTE_UPDATED}"
            FROM "{legacy_table}"
            """,
            (DEFAULT_USER_ID, NOTE_SOURCE_QUESTION),
        )
    else:
        conn.execute(
            f"""
            INSERT INTO "{TABLE_WRONG_NOTE}"
            ("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
            SELECT
                ?,
                ?,
                "{COL_YEAR}",
                "{COL_SUBJECT}",
                "{COL_QNO}",
                "{COL_NOTE_IMPORTANCE}",
                "{COL_NOTE_COMMENT}",
                "{COL_NOTE_UPDATED}"
            FROM "{legacy_table}"
            """,
            (DEFAULT_USER_ID, NOTE_SOURCE_QUESTION),
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
            "{COL_NOTE_SOURCE}" TEXT NOT NULL DEFAULT '{NOTE_SOURCE_QUESTION}',
            "{COL_YEAR}" INTEGER NOT NULL,
            "{COL_SUBJECT}" TEXT NOT NULL,
            "{COL_QNO}" INTEGER NOT NULL,
            "{COL_NOTE_IMPORTANCE}" TEXT NOT NULL DEFAULT '{DEFAULT_IMPORTANCE}',
            "{COL_NOTE_COMMENT}" TEXT NOT NULL DEFAULT '',
            "{COL_NOTE_UPDATED}" TEXT NOT NULL,
            UNIQUE ("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
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
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_NOTICE}" (
            "{COL_NOTICE_ID}" INTEGER PRIMARY KEY AUTOINCREMENT,
            "{COL_NOTICE_TITLE}" TEXT NOT NULL,
            "{COL_NOTICE_BODY}" TEXT NOT NULL,
            "{COL_NOTICE_AUTHOR}" TEXT NOT NULL DEFAULT '관리자',
            "{COL_NOTICE_PUBLISHED}" INTEGER NOT NULL DEFAULT 1,
            "{COL_NOTICE_CREATED}" TEXT NOT NULL,
            "{COL_NOTICE_UPDATED}" TEXT NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_QA_POST}" (
            "{COL_QA_POST_ID}" INTEGER PRIMARY KEY AUTOINCREMENT,
            "nickname" TEXT NOT NULL,
            "title" TEXT NOT NULL,
            "body" TEXT NOT NULL,
            "subject" TEXT NOT NULL DEFAULT '',
            "exam_year" INTEGER NOT NULL DEFAULT 0,
            "question_no" INTEGER NOT NULL DEFAULT 0,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{TABLE_QA_ANSWER}" (
            "{COL_QA_ANSWER_ID}" INTEGER PRIMARY KEY AUTOINCREMENT,
            "post_id" INTEGER NOT NULL,
            "nickname" TEXT NOT NULL,
            "body" TEXT NOT NULL,
            "created_at" TEXT NOT NULL,
            "updated_at" TEXT NOT NULL,
            FOREIGN KEY ("post_id") REFERENCES "{TABLE_QA_POST}"("{COL_QA_POST_ID}") ON DELETE CASCADE
        )
        """
    )
    notice_count = conn.execute(f'SELECT COUNT(*) FROM "{TABLE_NOTICE}"').fetchone()[0]
    if int(notice_count) == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            f"""
            INSERT INTO "{TABLE_NOTICE}"
            ("{COL_NOTICE_TITLE}", "{COL_NOTICE_BODY}", "{COL_NOTICE_AUTHOR}", "{COL_NOTICE_PUBLISHED}", "{COL_NOTICE_CREATED}", "{COL_NOTICE_UPDATED}")
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "공지",
                "문제/해설 데이터는 순차적으로 오픈됩니다.\n현재 모의고사 연도 선택은 2025년만 활성화되어 있습니다.",
                "관리자",
                1,
                now,
                now,
            ),
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


def fetch_notices(*, include_unpublished: bool = False) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        filters = []
        params: list[object] = []
        if not include_unpublished:
            filters.append(f'"{COL_NOTICE_PUBLISHED}" = 1')
        where_clause = f'WHERE {" AND ".join(filters)}' if filters else ""
        sql = f"""
            SELECT
                "{COL_NOTICE_ID}",
                "{COL_NOTICE_TITLE}",
                "{COL_NOTICE_BODY}",
                "{COL_NOTICE_AUTHOR}",
                "{COL_NOTICE_PUBLISHED}",
                "{COL_NOTICE_CREATED}",
                "{COL_NOTICE_UPDATED}"
            FROM "{TABLE_NOTICE}"
            {where_clause}
            ORDER BY "{COL_NOTICE_CREATED}" DESC, "{COL_NOTICE_ID}" DESC
        """
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [
        {
            "notice_id": int(notice_id),
            "title": normalize_question_text(title or ""),
            "body": normalize_question_text(body or ""),
            "author": normalize_question_text(author or ""),
            "is_published": int(is_published or 0),
            "created_at": created_at or "",
            "updated_at": updated_at or "",
        }
        for notice_id, title, body, author, is_published, created_at, updated_at in rows
    ]


def fetch_qa_posts(*, limit: int = 60) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        post_rows = conn.execute(
            f"""
            SELECT
                "{COL_QA_POST_ID}",
                "nickname",
                "title",
                "body",
                "subject",
                "exam_year",
                "question_no",
                "created_at",
                "updated_at"
            FROM "{TABLE_QA_POST}"
            ORDER BY "created_at" DESC, "{COL_QA_POST_ID}" DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        answer_rows = conn.execute(
            f"""
            SELECT
                "{COL_QA_ANSWER_ID}",
                "post_id",
                "nickname",
                "body",
                "created_at",
                "updated_at"
            FROM "{TABLE_QA_ANSWER}"
            ORDER BY "created_at" ASC, "{COL_QA_ANSWER_ID}" ASC
            """
        ).fetchall()
    finally:
        conn.close()

    answer_map: dict[int, list[dict]] = {}
    for answer_id, post_id, nickname, body, created_at, updated_at in answer_rows:
        answer_map.setdefault(int(post_id), []).append(
            {
                "id": int(answer_id),
                "nickname": normalize_question_text(nickname or ""),
                "body": normalize_question_text(body or ""),
                "created_at": created_at or "",
                "updated_at": updated_at or "",
            }
        )

    posts: list[dict] = []
    for post_id, nickname, title, body, subject, exam_year, question_no, created_at, updated_at in post_rows:
        normalized_subject = normalize_question_text(subject or "")
        posts.append(
            {
                "id": int(post_id),
                "nickname": normalize_question_text(nickname or ""),
                "title": normalize_question_text(title or ""),
                "body": normalize_question_text(body or ""),
                "subject": normalized_subject,
                "year": int(exam_year or 0),
                "question_no": int(question_no or 0),
                "created_at": created_at or "",
                "updated_at": updated_at or "",
                "answers": answer_map.get(int(post_id), []),
            }
        )
    return posts


def create_qa_post(*, nickname: str, title: str, body: str, subject: str = "", year: int = 0, question_no: int = 0) -> dict:
    normalized_nickname = normalize_question_text(nickname or "")[:40]
    normalized_title = normalize_question_text(title or "")[:160]
    normalized_body = normalize_question_text(body or "")
    normalized_subject = normalize_question_text(subject or "")
    if normalized_subject and normalized_subject not in SUBJECTS:
        raise ValueError("invalid subject")
    normalized_year = int(year or 0)
    normalized_question_no = int(question_no or 0)
    if not normalized_nickname:
        raise ValueError("nickname required")
    if not normalized_title or not normalized_body:
        raise ValueError("title/body required")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        cursor = conn.execute(
            f"""
            INSERT INTO "{TABLE_QA_POST}"
            ("nickname", "title", "body", "subject", "exam_year", "question_no", "created_at", "updated_at")
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_nickname,
                normalized_title,
                normalized_body,
                normalized_subject,
                normalized_year,
                normalized_question_no,
                now,
                now,
            ),
        )
        conn.commit()
        post_id = int(cursor.lastrowid)
    finally:
        conn.close()
    return {"id": post_id}


def create_qa_answer(*, post_id: int, nickname: str, body: str) -> dict:
    normalized_nickname = normalize_question_text(nickname or "")[:40]
    normalized_body = normalize_question_text(body or "")
    if not normalized_nickname or not normalized_body:
        raise ValueError("nickname/body required")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        exists = conn.execute(
            f'SELECT 1 FROM "{TABLE_QA_POST}" WHERE "{COL_QA_POST_ID}" = ? LIMIT 1',
            (int(post_id),),
        ).fetchone()
        if exists is None:
            raise LookupError("post not found")

        cursor = conn.execute(
            f"""
            INSERT INTO "{TABLE_QA_ANSWER}"
            ("post_id", "nickname", "body", "created_at", "updated_at")
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(post_id), normalized_nickname, normalized_body, now, now),
        )
        conn.commit()
        answer_id = int(cursor.lastrowid)
    finally:
        conn.close()
    return {"id": answer_id}


def upsert_notice(
    *,
    title: str,
    body: str,
    author: str,
    is_published: int,
    notice_id: int | None = None,
) -> dict:
    normalized_title = normalize_question_text(title or "")
    normalized_body = normalize_question_text(body or "")
    normalized_author = normalize_question_text(author or "") or "관리자"
    published_value = 1 if int(is_published or 0) else 0

    if not normalized_title or not normalized_body:
        raise ValueError("title/body required")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        if notice_id is None:
            cursor = conn.execute(
                f"""
                INSERT INTO "{TABLE_NOTICE}"
                ("{COL_NOTICE_TITLE}", "{COL_NOTICE_BODY}", "{COL_NOTICE_AUTHOR}", "{COL_NOTICE_PUBLISHED}", "{COL_NOTICE_CREATED}", "{COL_NOTICE_UPDATED}")
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (normalized_title, normalized_body, normalized_author, published_value, now, now),
            )
            notice_id = int(cursor.lastrowid)
        else:
            conn.execute(
                f"""
                UPDATE "{TABLE_NOTICE}"
                SET "{COL_NOTICE_TITLE}" = ?,
                    "{COL_NOTICE_BODY}" = ?,
                    "{COL_NOTICE_AUTHOR}" = ?,
                    "{COL_NOTICE_PUBLISHED}" = ?,
                    "{COL_NOTICE_UPDATED}" = ?
                WHERE "{COL_NOTICE_ID}" = ?
                """,
                (
                    normalized_title,
                    normalized_body,
                    normalized_author,
                    published_value,
                    now,
                    int(notice_id),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "notice_id": int(notice_id),
        "title": normalized_title,
        "body": normalized_body,
        "author": normalized_author,
        "is_published": published_value,
    }


def fetch_wrong_note_map(year: int, subject: str, user_id: str, source: str = NOTE_SOURCE_QUESTION) -> dict[str, dict]:
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_app_tables(conn)
        sql = f"""
            SELECT "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}"
            FROM "{TABLE_WRONG_NOTE}"
            WHERE "{COL_NOTE_USER}" = ? AND "{COL_NOTE_SOURCE}" = ? AND "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ?
        """
        rows = conn.execute(sql, (normalize_user_id(user_id), source, year, subject)).fetchall()
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
    source: str = "",
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
        if source:
            filters.append(f'n."{COL_NOTE_SOURCE}" = ?')
            params.append(source)
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
                n."{COL_NOTE_SOURCE}",
                q."{COL_STEM}",
                ox."{COL_OX_QUESTION}",
                ox."{COL_OX_ANSWER}",
                ox."{COL_OX_EXPLANATION}"
            FROM "{TABLE_WRONG_NOTE}" n
            LEFT JOIN "{TABLE_QUESTIONS}" q
              ON n."{COL_NOTE_SOURCE}" = '{NOTE_SOURCE_QUESTION}'
             AND q."{COL_YEAR}" = n."{COL_YEAR}"
             AND q."{COL_SUBJECT}" = n."{COL_SUBJECT}"
             AND q."{COL_QNO}" = n."{COL_QNO}"
            LEFT JOIN "{TABLE_OX}" ox
              ON n."{COL_NOTE_SOURCE}" = '{NOTE_SOURCE_OX}'
             AND ox."{COL_YEAR}" = n."{COL_YEAR}"
             AND ox."{COL_SUBJECT}" = n."{COL_SUBJECT}"
             AND ox."{COL_OX_QNO}" = n."{COL_QNO}"
            {where_clause}
            ORDER BY n."{COL_NOTE_UPDATED}" DESC, n."{COL_YEAR}" DESC, n."{COL_SUBJECT}" ASC, n."{COL_QNO}" ASC
        """
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    results: list[dict] = []
    for (
        year,
        note_subject,
        question_no,
        note_importance,
        note_comment,
        updated_at,
        note_source,
        stem,
        ox_question,
        ox_answer,
        ox_explanation,
    ) in rows:
        normalized_importance = (note_importance or "").strip().lower()
        if normalized_importance not in IMPORTANCE_LEVELS:
            normalized_importance = DEFAULT_IMPORTANCE
        preview_source = stem if note_source == NOTE_SOURCE_QUESTION else ox_question
        preview = normalize_question_text(preview_source or "")
        if len(preview) > 140:
            preview = f"{preview[:140]}..."
        results.append(
            {
                "year": int(year),
                "subject": note_subject,
                "question_no": int(question_no),
                "source": note_source or NOTE_SOURCE_QUESTION,
                "importance": normalized_importance,
                "comment": note_comment or "",
                "updated_at": updated_at or "",
                "question_preview": preview,
                "answer": (ox_answer or "") if note_source == NOTE_SOURCE_OX else "",
                "explanation": (ox_explanation or "") if note_source == NOTE_SOURCE_OX else "",
            }
        )
    return results


def upsert_wrong_note(
    *,
    user_id: str,
    source: str,
    year: int,
    subject: str,
    question_no: int,
    importance: str,
    comment: str,
) -> None:
    normalized_user_id = normalize_user_id(user_id)
    normalized_source = source if source in {NOTE_SOURCE_QUESTION, NOTE_SOURCE_OX} else NOTE_SOURCE_QUESTION
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
                WHERE "{COL_NOTE_USER}" = ? AND "{COL_NOTE_SOURCE}" = ? AND "{COL_YEAR}" = ? AND "{COL_SUBJECT}" = ? AND "{COL_QNO}" = ?
                """,
                (normalized_user_id, normalized_source, year, subject, question_no),
            )
        else:
            conn.execute(
                f"""
                INSERT INTO "{TABLE_WRONG_NOTE}"
                ("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}", "{COL_NOTE_IMPORTANCE}", "{COL_NOTE_COMMENT}", "{COL_NOTE_UPDATED}")
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT("{COL_NOTE_USER}", "{COL_NOTE_SOURCE}", "{COL_YEAR}", "{COL_SUBJECT}", "{COL_QNO}")
                DO UPDATE SET
                    "{COL_NOTE_IMPORTANCE}" = excluded."{COL_NOTE_IMPORTANCE}",
                    "{COL_NOTE_COMMENT}" = excluded."{COL_NOTE_COMMENT}",
                    "{COL_NOTE_UPDATED}" = excluded."{COL_NOTE_UPDATED}"
                """,
                (
                    normalized_user_id,
                    normalized_source,
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Notice-Admin-Key")
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
        if parsed.path == "/api/notices":
            self.handle_notices_api(parsed.query)
            return
        if parsed.path == "/api/qa/posts":
            self.handle_qa_posts_api(parsed.query)
            return
        if parsed.path == "/api/contact":
            self.handle_contact_api()
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
        if parsed.path == "/api/notices":
            self.handle_notice_upsert_api()
            return
        if parsed.path == "/api/qa/posts":
            self.handle_qa_post_create_api()
            return
        if parsed.path == "/api/qa/answers":
            self.handle_qa_answer_create_api()
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
        source = (params.get("source") or [""])[0].strip().lower()
        subject = (params.get("subject") or [""])[0]
        importance = (params.get("importance") or [""])[0].lower()
        comment = (params.get("comment") or [""])[0]
        if source and source not in {NOTE_SOURCE_QUESTION, NOTE_SOURCE_OX}:
            make_json_response(self, {"error": "invalid source"}, status=HTTPStatus.BAD_REQUEST)
            return
        if subject and subject not in SUBJECTS:
            make_json_response(self, {"error": "invalid subject"}, status=HTTPStatus.BAD_REQUEST)
            return
        if importance and importance not in IMPORTANCE_LEVELS:
            make_json_response(self, {"error": "invalid importance"}, status=HTTPStatus.BAD_REQUEST)
            return
        notes = fetch_wrong_notes(
            user_id=user_id,
            source=source,
            subject=subject,
            importance=importance,
            comment=comment,
        )
        make_json_response(self, {"user_id": user_id, "count": len(notes), "items": notes})

    def handle_wrong_notes_map_api(self, query: str) -> None:
        params = parse_qs(query)
        user_id = normalize_user_id((params.get("user_id") or [""])[0])
        source = (params.get("source") or [NOTE_SOURCE_QUESTION])[0].strip().lower() or NOTE_SOURCE_QUESTION
        year_text = (params.get("year") or [""])[0]
        subject = (params.get("subject") or [""])[0]
        try:
            year = int(year_text)
        except ValueError:
            make_json_response(self, {"error": "invalid year"}, status=HTTPStatus.BAD_REQUEST)
            return
        if source not in {NOTE_SOURCE_QUESTION, NOTE_SOURCE_OX}:
            make_json_response(self, {"error": "invalid source"}, status=HTTPStatus.BAD_REQUEST)
            return
        if subject not in SUBJECTS:
            make_json_response(self, {"error": "invalid subject"}, status=HTTPStatus.BAD_REQUEST)
            return
        note_map = fetch_wrong_note_map(year, subject, user_id, source)
        make_json_response(
            self,
            {"user_id": user_id, "year": year, "subject": subject, "source": source, "items": note_map},
        )

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
        source = str(payload.get("source") or NOTE_SOURCE_QUESTION)
        importance = str(payload.get("importance") or "")
        comment = str(payload.get("comment") or "")
        upsert_wrong_note(
            user_id=user_id,
            source=source,
            year=year,
            subject=subject,
            question_no=question_no,
            importance=importance,
            comment=comment,
        )
        make_json_response(self, {"ok": True, "user_id": user_id})

    def handle_notices_api(self, query: str) -> None:
        params = parse_qs(query)
        admin_mode = str((params.get("admin") or [""])[0]).strip() in {"1", "true", "yes"}
        include_unpublished = False
        if admin_mode:
            provided_key = str(self.headers.get("X-Notice-Admin-Key") or "").strip()
            include_unpublished = bool(NOTICE_ADMIN_KEY) and provided_key == NOTICE_ADMIN_KEY
        notices = fetch_notices(include_unpublished=include_unpublished)
        make_json_response(
            self,
            {
                "count": len(notices),
                "items": notices,
                "admin_mode": bool(include_unpublished),
            },
        )

    def handle_contact_api(self) -> None:
        make_json_response(
            self,
            {
                "email": CONTACT_EMAIL,
                "message": "잘못된 문제나 해설, 오탈자, 기능 오류가 있으면 아래 메일로 알려주세요.",
            },
        )

    def handle_qa_posts_api(self, query: str) -> None:
        params = parse_qs(query)
        limit_text = (params.get("limit") or ["60"])[0]
        try:
            limit = max(1, min(100, int(limit_text)))
        except ValueError:
            limit = 60
        posts = fetch_qa_posts(limit=limit)
        make_json_response(self, {"count": len(posts), "items": posts})

    def handle_notice_upsert_api(self) -> None:
        if not NOTICE_ADMIN_KEY:
            make_json_response(
                self,
                {"error": "notice admin key is not configured"},
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        provided_key = str(self.headers.get("X-Notice-Admin-Key") or "").strip()
        if provided_key != NOTICE_ADMIN_KEY:
            make_json_response(self, {"error": "forbidden"}, status=HTTPStatus.FORBIDDEN)
            return

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

        title = str(payload.get("title") or "")
        body = str(payload.get("body") or "")
        author = str(payload.get("author") or "")
        published = int(payload.get("is_published") or 0)
        notice_id_raw = payload.get("notice_id")
        notice_id = None
        if notice_id_raw is not None and str(notice_id_raw).strip():
            try:
                notice_id = int(notice_id_raw)
            except ValueError:
                make_json_response(self, {"error": "invalid notice_id"}, status=HTTPStatus.BAD_REQUEST)
                return

        try:
            saved = upsert_notice(
                title=title,
                body=body,
                author=author,
                is_published=published,
                notice_id=notice_id,
            )
        except ValueError as error:
            make_json_response(self, {"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        make_json_response(self, {"ok": True, "item": saved})

    def handle_qa_post_create_api(self) -> None:
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
            saved = create_qa_post(
                nickname=str(payload.get("nickname") or ""),
                title=str(payload.get("title") or ""),
                body=str(payload.get("body") or ""),
                subject=str(payload.get("subject") or ""),
                year=int(payload.get("year") or 0),
                question_no=int(payload.get("question_no") or 0),
            )
        except ValueError as error:
            make_json_response(self, {"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        make_json_response(self, {"ok": True, **saved})

    def handle_qa_answer_create_api(self) -> None:
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
            saved = create_qa_answer(
                post_id=int(payload.get("post_id") or 0),
                nickname=str(payload.get("nickname") or ""),
                body=str(payload.get("body") or ""),
            )
        except ValueError as error:
            make_json_response(self, {"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        except LookupError as error:
            make_json_response(self, {"error": str(error)}, status=HTTPStatus.NOT_FOUND)
            return
        make_json_response(self, {"ok": True, **saved})


def main() -> None:
    global NOTICE_ADMIN_KEY
    parser = argparse.ArgumentParser(description="Tax exam local web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--notice-admin-key", default="", help="Admin key for posting notices")
    args = parser.parse_args()
    if str(args.notice_admin_key or "").strip():
        NOTICE_ADMIN_KEY = str(args.notice_admin_key).strip()

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
