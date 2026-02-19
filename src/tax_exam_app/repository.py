from __future__ import annotations

import json
from dataclasses import asdict
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .models import NoteRecord, ProcessedQuestion, RawQuestion


class SQLiteRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no INTEGER NOT NULL,
                    raw_text TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_stage TEXT NOT NULL,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    choices TEXT NOT NULL,
                    answer_key TEXT NOT NULL,
                    explanation_text TEXT NOT NULL,
                    updated_flag INTEGER NOT NULL,
                    legal_refs TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    needs_human_review INTEGER NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    source_url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS question_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    version_no INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    choices TEXT NOT NULL,
                    answer_key TEXT NOT NULL,
                    explanation_text TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(question_id, version_no),
                    FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS batch_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    params TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    counts TEXT,
                    logs_path TEXT
                );

                CREATE TABLE IF NOT EXISTS user_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    question_id INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    memo TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_reviewed_at TEXT,
                    UNIQUE(user_id, question_id),
                    FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS bank_user_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no_exam INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    memo TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_reviewed_at TEXT,
                    UNIQUE(user_id, exam_year, subject_code, question_no_exam)
                );

                CREATE TABLE IF NOT EXISTS bank_user_favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no_exam INTEGER NOT NULL,
                    color TEXT NOT NULL,
                    memo TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, exam_year, subject_code, question_no_exam)
                );

                CREATE TABLE IF NOT EXISTS exam_question_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_year INTEGER NOT NULL,
                    session_no INTEGER NOT NULL,
                    booklet_type TEXT NOT NULL,
                    subject_name TEXT NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no_exam INTEGER NOT NULL,
                    question_no_subject INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    choices_json TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    official_answer TEXT,
                    service_answer TEXT,
                    review_flag INTEGER NOT NULL DEFAULT 0,
                    review_reason TEXT,
                    explanation_text TEXT,
                    explanation_model TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exam_year, subject_code, question_no_exam, booklet_type)
                );

                CREATE TABLE IF NOT EXISTS exam_explanation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_bank_id INTEGER NOT NULL,
                    explanation_text TEXT NOT NULL,
                    explanation_model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(question_bank_id) REFERENCES exam_question_bank(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS exam_choice_ox_bank (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_bank_id INTEGER NOT NULL,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no_exam INTEGER NOT NULL,
                    choice_no INTEGER NOT NULL,
                    choice_text TEXT NOT NULL,
                    choice_explanation_text TEXT,
                    is_ox_eligible INTEGER NOT NULL,
                    expected_ox TEXT,
                    stem_polarity TEXT,
                    judge_reason TEXT NOT NULL,
                    judge_confidence TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(question_bank_id, choice_no),
                    FOREIGN KEY(question_bank_id) REFERENCES exam_question_bank(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS app_users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_choice_visibility (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no_exam INTEGER NOT NULL,
                    choice_no INTEGER NOT NULL,
                    hidden INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, exam_year, subject_code, question_no_exam, choice_no),
                    FOREIGN KEY(user_id) REFERENCES app_users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_exam_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    exam_year INTEGER,
                    subject_code TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    answered_questions INTEGER NOT NULL,
                    correct_count INTEGER NOT NULL,
                    score_100 REAL NOT NULL,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    finished_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES app_users(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_exam_attempt_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id INTEGER NOT NULL,
                    item_kind TEXT NOT NULL,
                    question_bank_id INTEGER,
                    ox_item_id INTEGER,
                    exam_year INTEGER NOT NULL,
                    subject_code TEXT NOT NULL,
                    question_no_exam INTEGER NOT NULL,
                    choice_no INTEGER,
                    selected_answer TEXT,
                    correct_answer TEXT,
                    is_correct INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(attempt_id) REFERENCES user_exam_attempts(id) ON DELETE CASCADE,
                    FOREIGN KEY(question_bank_id) REFERENCES exam_question_bank(id) ON DELETE SET NULL,
                    FOREIGN KEY(ox_item_id) REFERENCES exam_choice_ox_bank(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS user_subject_recent_scores (
                    user_id TEXT NOT NULL,
                    subject_code TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    last_attempt_id INTEGER NOT NULL,
                    last_exam_year INTEGER,
                    last_score_100 REAL NOT NULL,
                    attempts_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, subject_code, mode),
                    FOREIGN KEY(user_id) REFERENCES app_users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY(last_attempt_id) REFERENCES user_exam_attempts(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_choice_visibility_user_subject
                    ON user_choice_visibility(user_id, exam_year, subject_code, question_no_exam);
                CREATE INDEX IF NOT EXISTS idx_attempts_user_subject
                    ON user_exam_attempts(user_id, subject_code, mode, finished_at DESC);
                CREATE INDEX IF NOT EXISTS idx_attempt_answers_attempt
                    ON user_exam_attempt_answers(attempt_id);
                """
            )
            try:
                conn.execute("ALTER TABLE exam_choice_ox_bank ADD COLUMN choice_explanation_text TEXT")
            except sqlite3.OperationalError:
                pass

    def insert_raw_questions(self, raws: list[RawQuestion]) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO raw_questions
                (exam_year, subject_code, question_no, raw_text, source_url, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.exam_year,
                        r.subject_code,
                        r.question_no,
                        r.raw_text,
                        r.source_url,
                        r.content_hash,
                        now,
                    )
                    for r in raws
                ],
            )

    def fetch_raw_questions(self, years: list[int] | None = None, subjects: list[str] | None = None) -> list[RawQuestion]:
        q = "SELECT exam_year, subject_code, question_no, raw_text, source_url, content_hash FROM raw_questions WHERE 1=1"
        params: list[object] = []

        if years:
            q += f" AND exam_year IN ({','.join(['?'] * len(years))})"
            params.extend(years)
        if subjects:
            q += f" AND subject_code IN ({','.join(['?'] * len(subjects))})"
            params.extend(subjects)

        q += " ORDER BY exam_year, subject_code, question_no"

        with self._conn() as conn:
            rows = conn.execute(q, params).fetchall()
        return [
            RawQuestion(
                exam_year=int(r["exam_year"]),
                subject_code=str(r["subject_code"]),
                question_no=int(r["question_no"]),
                raw_text=str(r["raw_text"]),
                source_url=str(r["source_url"]),
                content_hash=str(r["content_hash"]),
            )
            for r in rows
        ]

    def start_batch(self, mode: str, params: dict) -> int:
        started_at = datetime.utcnow().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO batch_runs (mode, params, status, started_at) VALUES (?, ?, 'running', ?)",
                (mode, json.dumps(params, ensure_ascii=False), started_at),
            )
            return int(cur.lastrowid)

    def finish_batch(self, batch_id: int, status: str, counts: dict[str, int]) -> None:
        finished_at = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE batch_runs SET status = ?, finished_at = ?, counts = ? WHERE id = ?",
                (status, finished_at, json.dumps(counts), batch_id),
            )

    def upsert_processed_question(self, payload: ProcessedQuestion) -> int:
        now = datetime.utcnow().isoformat()
        legal_refs_json = json.dumps([asdict(ref) for ref in payload.decision.legal_refs], ensure_ascii=False)
        choices_json = json.dumps(payload.revised.structured.choices, ensure_ascii=False)

        with self._conn() as conn:
            row = conn.execute("SELECT id FROM questions WHERE content_hash = ?", (payload.raw.content_hash,)).fetchone()

            if row:
                question_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE questions
                    SET question_text = ?, choices = ?, answer_key = ?, explanation_text = ?,
                        updated_flag = ?, legal_refs = ?, confidence = ?, needs_human_review = ?,
                        status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload.revised.structured.question_text,
                        choices_json,
                        payload.revised.structured.answer_key,
                        payload.explanation.explanation_text,
                        int(payload.revised.updated_flag),
                        legal_refs_json,
                        payload.decision.confidence,
                        int(payload.validation.needs_human_review),
                        payload.validation.status,
                        now,
                        question_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO questions
                    (exam_stage, exam_year, subject_code, question_no, question_text,
                     choices, answer_key, explanation_text, updated_flag, legal_refs,
                     confidence, needs_human_review, content_hash, source_url, status,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.revised.structured.exam_stage,
                        payload.revised.structured.exam_year,
                        payload.revised.structured.subject_code,
                        payload.revised.structured.question_no,
                        payload.revised.structured.question_text,
                        choices_json,
                        payload.revised.structured.answer_key,
                        payload.explanation.explanation_text,
                        int(payload.revised.updated_flag),
                        legal_refs_json,
                        payload.decision.confidence,
                        int(payload.validation.needs_human_review),
                        payload.raw.content_hash,
                        payload.raw.source_url,
                        payload.validation.status,
                        now,
                        now,
                    ),
                )
                question_id = int(cur.lastrowid)

            version_no = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version_no), 0) + 1 AS next_ver FROM question_versions WHERE question_id = ?",
                    (question_id,),
                ).fetchone()["next_ver"]
            )
            conn.execute(
                """
                INSERT INTO question_versions
                (question_id, version_no, question_text, choices, answer_key, explanation_text, change_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    version_no,
                    payload.revised.structured.question_text,
                    choices_json,
                    payload.revised.structured.answer_key,
                    payload.explanation.explanation_text,
                    payload.revised.change_summary,
                    now,
                ),
            )
        return question_id

    def list_questions(
        self,
        limit: int = 50,
        status: str | None = None,
        subject_code: str | None = None,
        exam_year: int | None = None,
    ) -> list[dict]:
        q = "SELECT * FROM questions WHERE 1=1"
        params: list[object] = []
        if status:
            q += " AND status = ?"
            params.append(status)
        if subject_code:
            q += " AND subject_code = ?"
            params.append(subject_code)
        if exam_year:
            q += " AND exam_year = ?"
            params.append(exam_year)

        q += " ORDER BY exam_year DESC, subject_code, question_no LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row_to_question(r) for r in rows]

    def get_question(self, question_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return self._row_to_question(row) if row else None

    def list_batch_runs(self, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, mode, status, started_at, finished_at, counts FROM batch_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "mode": str(r["mode"]),
                "status": str(r["status"]),
                "started_at": str(r["started_at"]),
                "finished_at": r["finished_at"],
                "counts": json.loads(r["counts"]) if r["counts"] else {},
            }
            for r in rows
        ]

    def upsert_note(self, note: NoteRecord) -> None:
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(note.tags, ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO user_notes (user_id, question_id, state, memo, tags, source, created_at, updated_at, last_reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, question_id)
                DO UPDATE SET state=excluded.state,
                              memo=excluded.memo,
                              tags=excluded.tags,
                              source=excluded.source,
                              updated_at=excluded.updated_at,
                              last_reviewed_at=excluded.last_reviewed_at
                """,
                (
                    note.user_id,
                    note.question_id,
                    note.state,
                    note.memo,
                    tags_json,
                    note.source,
                    now,
                    now,
                    now,
                ),
            )

    def list_notes(self, user_id: str = "local-user") -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM user_notes WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "user_id": str(r["user_id"]),
                "question_id": int(r["question_id"]),
                "state": str(r["state"]),
                "memo": str(r["memo"]),
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "source": str(r["source"]),
                "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
                "last_reviewed_at": r["last_reviewed_at"],
            }
            for r in rows
        ]

    def ensure_user(self, user_id: str, display_name: str | None = None) -> None:
        now = datetime.utcnow().isoformat()
        safe_name = (display_name or user_id or "user").strip()[:80] or "user"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO app_users (user_id, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    display_name=excluded.display_name,
                    updated_at=excluded.updated_at
                """,
                (user_id, safe_name, now, now),
            )

    def set_choice_visibility(
        self,
        user_id: str,
        exam_year: int,
        subject_code: str,
        question_no_exam: int,
        choice_no: int,
        hidden: bool,
    ) -> None:
        self.ensure_user(user_id=user_id)
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO user_choice_visibility (
                    user_id, exam_year, subject_code, question_no_exam, choice_no, hidden, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, exam_year, subject_code, question_no_exam, choice_no)
                DO UPDATE SET
                    hidden=excluded.hidden,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    exam_year,
                    subject_code,
                    question_no_exam,
                    choice_no,
                    int(hidden),
                    now,
                ),
            )

    def get_choice_visibility(
        self,
        user_id: str,
        exam_year: int,
        subject_code: str,
    ) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT question_no_exam, choice_no, hidden, updated_at
                FROM user_choice_visibility
                WHERE user_id=? AND exam_year=? AND subject_code=?
                ORDER BY question_no_exam, choice_no
                """,
                (user_id, exam_year, subject_code),
            ).fetchall()
        return [
            {
                "question_no_exam": int(r["question_no_exam"]),
                "choice_no": int(r["choice_no"]),
                "hidden": bool(int(r["hidden"])),
                "updated_at": str(r["updated_at"]),
            }
            for r in rows
        ]

    def record_exam_attempt(
        self,
        user_id: str,
        mode: str,
        subject_code: str,
        total_questions: int,
        answered_questions: int,
        correct_count: int,
        score_100: float,
        details: list[dict],
        exam_year: int | None = None,
        started_at: str | None = None,
        duration_seconds: int = 0,
    ) -> int:
        self.ensure_user(user_id=user_id)
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO user_exam_attempts (
                    user_id, mode, exam_year, subject_code, total_questions, answered_questions,
                    correct_count, score_100, duration_seconds, started_at, finished_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    mode,
                    exam_year,
                    subject_code,
                    total_questions,
                    answered_questions,
                    correct_count,
                    score_100,
                    max(0, int(duration_seconds)),
                    started_at,
                    now,
                    now,
                ),
            )
            attempt_id = int(cur.lastrowid)

            rows: list[tuple] = []
            for d in details:
                item_kind = "ox_item" if mode == "ox" else "question"
                rows.append(
                    (
                        attempt_id,
                        item_kind,
                        d.get("question_id"),
                        d.get("id"),
                        int(d.get("exam_year") or exam_year or 0),
                        str(d.get("subject_code") or subject_code),
                        int(d.get("question_no_exam") or 0),
                        int(d["choice_no"]) if d.get("choice_no") is not None else None,
                        str(d.get("selected_answer") or d.get("selected_ox") or ""),
                        str(d.get("correct_answer") or d.get("expected_ox") or ""),
                        int(bool(d.get("is_correct"))),
                        now,
                    )
                )
            if rows:
                conn.executemany(
                    """
                    INSERT INTO user_exam_attempt_answers (
                        attempt_id, item_kind, question_bank_id, ox_item_id,
                        exam_year, subject_code, question_no_exam, choice_no,
                        selected_answer, correct_answer, is_correct, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )

            stat_row = conn.execute(
                """
                SELECT attempts_count
                FROM user_subject_recent_scores
                WHERE user_id=? AND subject_code=? AND mode=?
                """,
                (user_id, subject_code, mode),
            ).fetchone()
            attempts_count = int(stat_row["attempts_count"]) + 1 if stat_row else 1
            conn.execute(
                """
                INSERT INTO user_subject_recent_scores (
                    user_id, subject_code, mode, last_attempt_id, last_exam_year, last_score_100, attempts_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, subject_code, mode)
                DO UPDATE SET
                    last_attempt_id=excluded.last_attempt_id,
                    last_exam_year=excluded.last_exam_year,
                    last_score_100=excluded.last_score_100,
                    attempts_count=excluded.attempts_count,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    subject_code,
                    mode,
                    attempt_id,
                    exam_year,
                    float(score_100),
                    attempts_count,
                    now,
                ),
            )
        return attempt_id

    def list_user_subject_recent_scores(self, user_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT s.user_id, s.subject_code, s.mode, s.last_attempt_id, s.last_exam_year,
                       s.last_score_100, s.attempts_count, s.updated_at,
                       COALESCE(MAX(q.subject_name), s.subject_code) AS subject_name
                FROM user_subject_recent_scores s
                LEFT JOIN exam_question_bank q ON q.subject_code = s.subject_code
                WHERE s.user_id=?
                GROUP BY s.user_id, s.subject_code, s.mode, s.last_attempt_id, s.last_exam_year,
                         s.last_score_100, s.attempts_count, s.updated_at
                ORDER BY s.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "user_id": str(r["user_id"]),
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]),
                "mode": str(r["mode"]),
                "last_attempt_id": int(r["last_attempt_id"]),
                "last_exam_year": int(r["last_exam_year"]) if r["last_exam_year"] is not None else None,
                "last_score_100": float(r["last_score_100"]),
                "attempts_count": int(r["attempts_count"]),
                "updated_at": str(r["updated_at"]),
            }
            for r in rows
        ]

    def get_learning_dashboard_scores(self, user_id: str) -> dict:
        categories = ["재정학", "회계학", "세법학", "선택법"]

        classify_expr = """
            CASE
                WHEN COALESCE(m.subject_name, a.subject_code) LIKE '%재정학%' THEN '재정학'
                WHEN COALESCE(m.subject_name, a.subject_code) LIKE '%회계학%' THEN '회계학'
                WHEN COALESCE(m.subject_name, a.subject_code) LIKE '%세법학%' THEN '세법학'
                WHEN COALESCE(m.subject_name, a.subject_code) LIKE '%상법%'
                  OR COALESCE(m.subject_name, a.subject_code) LIKE '%민법%'
                  OR COALESCE(m.subject_name, a.subject_code) LIKE '%행정소송법%' THEN '선택법'
                ELSE NULL
            END
        """

        with self._conn() as conn:
            my_rows = conn.execute(
                f"""
                WITH subject_name_map AS (
                    SELECT subject_code, MAX(subject_name) AS subject_name
                    FROM exam_question_bank
                    GROUP BY subject_code
                ),
                ranked AS (
                    SELECT
                        {classify_expr} AS category,
                        a.score_100 AS score_100,
                        a.finished_at AS finished_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY {classify_expr}
                            ORDER BY a.finished_at DESC, a.id DESC
                        ) AS rn
                    FROM user_exam_attempts a
                    LEFT JOIN subject_name_map m ON m.subject_code = a.subject_code
                    WHERE a.user_id = ?
                      AND a.mode = 'mock'
                )
                SELECT category, score_100
                FROM ranked
                WHERE category IS NOT NULL AND rn = 1
                """,
                (user_id,),
            ).fetchall()

            avg_rows = conn.execute(
                f"""
                WITH subject_name_map AS (
                    SELECT subject_code, MAX(subject_name) AS subject_name
                    FROM exam_question_bank
                    GROUP BY subject_code
                )
                SELECT
                    {classify_expr} AS category,
                    AVG(a.score_100) AS avg_score
                FROM user_exam_attempts a
                LEFT JOIN subject_name_map m ON m.subject_code = a.subject_code
                WHERE a.mode = 'mock'
                  AND a.total_questions = 40
                  AND a.answered_questions = 40
                GROUP BY category
                """,
            ).fetchall()

        my_map = {str(r["category"]): float(r["score_100"]) for r in my_rows if r["category"] is not None}
        avg_map = {str(r["category"]): float(r["avg_score"]) for r in avg_rows if r["category"] is not None and r["avg_score"] is not None}

        return {
            "categories": categories,
            "my_recent_scores": my_map,
            "overall_avg_scores": avg_map,
        }

    def upsert_bank_note(
        self,
        user_id: str,
        exam_year: int,
        subject_code: str,
        question_no_exam: int,
        state: str,
        memo: str = "",
        tags: list[str] | None = None,
        source: str = "mock",
    ) -> None:
        self.ensure_user(user_id=user_id)
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO bank_user_notes (
                    user_id, exam_year, subject_code, question_no_exam,
                    state, memo, tags, source, created_at, updated_at, last_reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, exam_year, subject_code, question_no_exam)
                DO UPDATE SET
                    state=excluded.state,
                    memo=excluded.memo,
                    tags=excluded.tags,
                    source=excluded.source,
                    updated_at=excluded.updated_at,
                    last_reviewed_at=excluded.last_reviewed_at
                """,
                (
                    user_id,
                    exam_year,
                    subject_code,
                    question_no_exam,
                    state,
                    memo,
                    tags_json,
                    source,
                    now,
                    now,
                    now,
                ),
            )

    def list_bank_notes(
        self,
        user_id: str = "local-user",
        exam_year: int | None = None,
        subject_code: str | None = None,
    ) -> list[dict]:
        query = """
            SELECT n.*, b.subject_name, b.question_text, b.explanation_text, b.service_answer
            FROM bank_user_notes n
            LEFT JOIN exam_question_bank b
              ON b.exam_year = n.exam_year
             AND b.subject_code = n.subject_code
             AND b.question_no_exam = n.question_no_exam
            WHERE n.user_id = ?
        """
        params: list[object] = [user_id]
        if exam_year is not None:
            query += " AND n.exam_year = ?"
            params.append(exam_year)
        if subject_code:
            query += " AND n.subject_code = ?"
            params.append(subject_code)
        query += " ORDER BY n.updated_at DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            fav_query = """
                SELECT f.*, b.subject_name, b.question_text, b.explanation_text, b.service_answer
                FROM bank_user_favorites f
                LEFT JOIN exam_question_bank b
                  ON b.exam_year = f.exam_year
                 AND b.subject_code = f.subject_code
                 AND b.question_no_exam = f.question_no_exam
                WHERE f.user_id = ?
            """
            fav_params: list[object] = [user_id]
            if exam_year is not None:
                fav_query += " AND f.exam_year = ?"
                fav_params.append(exam_year)
            if subject_code:
                fav_query += " AND f.subject_code = ?"
                fav_params.append(subject_code)
            fav_query += " ORDER BY f.updated_at DESC"
            fav_rows = conn.execute(fav_query, fav_params).fetchall()

        base_rows = [
            {
                "id": int(r["id"]),
                "user_id": str(r["user_id"]),
                "exam_year": int(r["exam_year"]),
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]) if r["subject_name"] is not None else "",
                "question_no_exam": int(r["question_no_exam"]),
                "state": str(r["state"]),
                "memo": str(r["memo"]),
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "source": str(r["source"]),
                "question_text": str(r["question_text"]) if r["question_text"] is not None else "",
                "service_answer": str(r["service_answer"]) if r["service_answer"] is not None else "",
                "explanation_text": str(r["explanation_text"]) if r["explanation_text"] is not None else "",
                "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
                "last_reviewed_at": r["last_reviewed_at"],
            }
            for r in rows
        ]
        fav_list = [
            {
                "id": int(r["id"]),
                "user_id": str(r["user_id"]),
                "exam_year": int(r["exam_year"]),
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]) if r["subject_name"] is not None else "",
                "question_no_exam": int(r["question_no_exam"]),
                "state": f"favorite_{r['color']}",
                "memo": str(r["memo"]),
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "source": str(r["source"]),
                "question_text": str(r["question_text"]) if r["question_text"] is not None else "",
                "service_answer": str(r["service_answer"]) if r["service_answer"] is not None else "",
                "explanation_text": str(r["explanation_text"]) if r["explanation_text"] is not None else "",
                "created_at": str(r["created_at"]),
                "updated_at": str(r["updated_at"]),
                "last_reviewed_at": None,
            }
            for r in fav_rows
        ]
        merged = base_rows + fav_list
        merged.sort(key=lambda x: x["updated_at"], reverse=True)
        return merged

    def delete_bank_note(
        self,
        user_id: str,
        exam_year: int,
        subject_code: str,
        question_no_exam: int,
        state_prefix: str | None = None,
    ) -> int:
        with self._conn() as conn:
            if state_prefix:
                result = conn.execute(
                    """
                    DELETE FROM bank_user_notes
                    WHERE user_id=? AND exam_year=? AND subject_code=? AND question_no_exam=?
                      AND state LIKE ?
                    """,
                    (user_id, exam_year, subject_code, question_no_exam, f"{state_prefix}%"),
                )
                return int(result.rowcount)
            result = conn.execute(
                """
                DELETE FROM bank_user_notes
                WHERE user_id=? AND exam_year=? AND subject_code=? AND question_no_exam=?
                """,
                (user_id, exam_year, subject_code, question_no_exam),
            )
            return int(result.rowcount)

    def upsert_bank_favorite(
        self,
        user_id: str,
        exam_year: int,
        subject_code: str,
        question_no_exam: int,
        color: str,
        memo: str = "",
        tags: list[str] | None = None,
        source: str = "mock",
    ) -> None:
        self.ensure_user(user_id=user_id)
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO bank_user_favorites (
                    user_id, exam_year, subject_code, question_no_exam,
                    color, memo, tags, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, exam_year, subject_code, question_no_exam)
                DO UPDATE SET
                    color=excluded.color,
                    memo=excluded.memo,
                    tags=excluded.tags,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    exam_year,
                    subject_code,
                    question_no_exam,
                    color,
                    memo,
                    tags_json,
                    source,
                    now,
                    now,
                ),
            )

    def delete_bank_favorite(
        self,
        user_id: str,
        exam_year: int,
        subject_code: str,
        question_no_exam: int,
    ) -> int:
        with self._conn() as conn:
            result = conn.execute(
                """
                DELETE FROM bank_user_favorites
                WHERE user_id=? AND exam_year=? AND subject_code=? AND question_no_exam=?
                """,
                (user_id, exam_year, subject_code, question_no_exam),
            )
            return int(result.rowcount)

    def list_ox_subject_options(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT o.subject_code,
                       COALESCE(MAX(q.subject_name), o.subject_code) AS subject_name,
                       COUNT(*) AS total_items
                FROM exam_choice_ox_bank o
                LEFT JOIN exam_question_bank q
                  ON q.exam_year = o.exam_year
                 AND q.subject_code = o.subject_code
                 AND q.question_no_exam = o.question_no_exam
                WHERE o.is_ox_eligible = 1
                GROUP BY o.subject_code
                ORDER BY subject_name
                """
            ).fetchall()
        return [
            {
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]),
                "total_items": int(r["total_items"]),
            }
            for r in rows
        ]

    def get_ox_questions(self, subject_code: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT o.id, o.exam_year, o.subject_code, o.question_no_exam, o.choice_no, o.choice_text,
                       o.choice_explanation_text, o.expected_ox, o.judge_reason, q.subject_name
                FROM exam_choice_ox_bank o
                LEFT JOIN exam_question_bank q
                  ON q.exam_year = o.exam_year
                 AND q.subject_code = o.subject_code
                 AND q.question_no_exam = o.question_no_exam
                WHERE o.subject_code = ?
                  AND o.is_ox_eligible = 1
                ORDER BY o.exam_year DESC, o.question_no_exam, o.choice_no
                """,
                (subject_code,),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "exam_year": int(r["exam_year"]),
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]) if r["subject_name"] is not None else str(r["subject_code"]),
                "question_no_exam": int(r["question_no_exam"]),
                "choice_no": int(r["choice_no"]),
                "choice_text": str(r["choice_text"]),
                "choice_explanation_text": str(r["choice_explanation_text"] or ""),
                "judge_reason": str(r["judge_reason"] or ""),
                "expected_ox": str(r["expected_ox"]) if r["expected_ox"] is not None else "",
            }
            for r in rows
        ]

    def get_user_ox_item_stats(self, user_id: str, subject_code: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.ox_item_id AS ox_item_id,
                    COUNT(*) AS solved_count,
                    SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
                FROM user_exam_attempt_answers a
                JOIN user_exam_attempts t ON t.id = a.attempt_id
                WHERE a.item_kind = 'ox_item'
                  AND t.user_id = ?
                  AND a.subject_code = ?
                  AND a.ox_item_id IS NOT NULL
                GROUP BY a.ox_item_id
                """,
                (user_id, subject_code),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            solved = int(row["solved_count"] or 0)
            correct = int(row["correct_count"] or 0)
            acc = round((correct / solved) * 100, 1) if solved > 0 else 0.0
            out.append(
                {
                    "ox_item_id": int(row["ox_item_id"]),
                    "solved_count": solved,
                    "correct_count": correct,
                    "accuracy": acc,
                }
            )
        return out

    def get_user_mock_question_stats(self, user_id: str, exam_year: int, subject_code: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.question_bank_id AS question_id,
                    COUNT(*) AS solved_count,
                    SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_count
                FROM user_exam_attempt_answers a
                JOIN user_exam_attempts t ON t.id = a.attempt_id
                WHERE a.item_kind = 'question'
                  AND t.user_id = ?
                  AND a.exam_year = ?
                  AND a.subject_code = ?
                  AND a.question_bank_id IS NOT NULL
                GROUP BY a.question_bank_id
                """,
                (user_id, exam_year, subject_code),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            solved = int(row["solved_count"] or 0)
            correct = int(row["correct_count"] or 0)
            acc = round((correct / solved) * 100, 1) if solved > 0 else 0.0
            out.append(
                {
                    "question_id": int(row["question_id"]),
                    "solved_count": solved,
                    "correct_count": correct,
                    "accuracy": acc,
                }
            )
        return out

    def get_dashboard_stats(self) -> dict:
        with self._conn() as conn:
            total = int(conn.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"])
            published = int(conn.execute("SELECT COUNT(*) AS c FROM questions WHERE status='published'").fetchone()["c"])
            review_required = int(
                conn.execute("SELECT COUNT(*) AS c FROM questions WHERE status='review_required'").fetchone()["c"]
            )
            notes = int(conn.execute("SELECT COUNT(*) AS c FROM user_notes").fetchone()["c"])

        return {
            "total_questions": total,
            "published_questions": published,
            "review_required_questions": review_required,
            "notes_count": notes,
        }

    def list_mock_options(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT exam_year, subject_code, subject_name,
                       COUNT(*) AS total_questions,
                       SUM(CASE WHEN service_answer IS NOT NULL AND service_answer <> '' THEN 1 ELSE 0 END) AS answered_questions
                FROM exam_question_bank
                GROUP BY exam_year, subject_code, subject_name
                ORDER BY exam_year DESC, subject_name
                """
            ).fetchall()
        return [
            {
                "exam_year": int(r["exam_year"]),
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]),
                "total_questions": int(r["total_questions"]),
                "answered_questions": int(r["answered_questions"] or 0),
            }
            for r in rows
        ]

    def get_mock_questions(self, exam_year: int, subject_code: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, exam_year, subject_code, subject_name, question_no_exam, question_no_subject,
                       question_text, choices_json, service_answer, explanation_text
                FROM exam_question_bank
                WHERE exam_year = ? AND subject_code = ?
                ORDER BY question_no_exam
                """,
                (exam_year, subject_code),
            ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "exam_year": int(r["exam_year"]),
                "subject_code": str(r["subject_code"]),
                "subject_name": str(r["subject_name"]),
                "question_no_exam": int(r["question_no_exam"]),
                "question_no_subject": int(r["question_no_subject"]),
                "question_text": str(r["question_text"]),
                "choices": json.loads(r["choices_json"]),
                "service_answer": str(r["service_answer"]) if r["service_answer"] is not None else "",
                "explanation_text": str(r["explanation_text"]) if r["explanation_text"] is not None else "",
            }
            for r in rows
        ]

    def get_bank_question_explanation(self, question_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, exam_year, subject_code, subject_name, question_no_exam,
                       question_text, service_answer, official_answer, explanation_text
                FROM exam_question_bank
                WHERE id = ?
                """,
                (question_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "exam_year": int(row["exam_year"]),
            "subject_code": str(row["subject_code"]),
            "subject_name": str(row["subject_name"]),
            "question_no_exam": int(row["question_no_exam"]),
            "question_text": str(row["question_text"]),
            "correct_answer": str(row["service_answer"] or row["official_answer"] or ""),
            "explanation_text": str(row["explanation_text"] or ""),
        }

    def get_ox_candidates(self, exam_year: int, subject_code: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT o.question_no_exam, o.choice_no, o.choice_text, o.expected_ox,
                       o.judge_reason, o.judge_confidence
                FROM exam_choice_ox_bank o
                WHERE o.exam_year = ?
                  AND o.subject_code = ?
                  AND o.is_ox_eligible = 1
                ORDER BY o.question_no_exam, o.choice_no
                """,
                (exam_year, subject_code),
            ).fetchall()
        return [
            {
                "question_no_exam": int(r["question_no_exam"]),
                "choice_no": int(r["choice_no"]),
                "choice_text": str(r["choice_text"]),
                "expected_ox": str(r["expected_ox"]) if r["expected_ox"] is not None else None,
                "judge_reason": str(r["judge_reason"]),
                "judge_confidence": str(r["judge_confidence"]),
            }
            for r in rows
        ]

    def _row_to_question(self, row: sqlite3.Row) -> dict:
        return {
            "id": int(row["id"]),
            "exam_stage": str(row["exam_stage"]),
            "exam_year": int(row["exam_year"]),
            "subject_code": str(row["subject_code"]),
            "question_no": int(row["question_no"]),
            "question_text": str(row["question_text"]),
            "choices": json.loads(row["choices"]),
            "answer_key": str(row["answer_key"]),
            "explanation_text": str(row["explanation_text"]),
            "updated_flag": bool(row["updated_flag"]),
            "legal_refs": json.loads(row["legal_refs"]),
            "confidence": str(row["confidence"]),
            "needs_human_review": bool(row["needs_human_review"]),
            "content_hash": str(row["content_hash"]),
            "source_url": str(row["source_url"]),
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

