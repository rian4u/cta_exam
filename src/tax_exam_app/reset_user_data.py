from __future__ import annotations

import argparse
import json
import sqlite3


USER_TABLES = [
    "user_exam_attempt_answers",
    "user_exam_attempts",
    "user_subject_recent_scores",
    "user_choice_visibility",
    "bank_user_notes",
    "bank_user_favorites",
    "user_notes",
    "app_users",
]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def reset_all_users(db_path: str) -> dict[str, int]:
    deleted: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for table in USER_TABLES:
            if not _table_exists(conn, table):
                continue
            cursor = conn.execute(f"DELETE FROM {table}")
            deleted[table] = int(cursor.rowcount if cursor.rowcount is not None else 0)
        conn.commit()
    return deleted


def reset_one_user(db_path: str, user_id: str) -> dict[str, int]:
    deleted: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for table in USER_TABLES:
            if not _table_exists(conn, table):
                continue
            if table == "user_exam_attempt_answers":
                cursor = conn.execute(
                    """
                    DELETE FROM user_exam_attempt_answers
                    WHERE attempt_id IN (
                        SELECT id FROM user_exam_attempts WHERE user_id=?
                    )
                    """,
                    (user_id,),
                )
            elif table in {
                "user_exam_attempts",
                "user_subject_recent_scores",
                "user_choice_visibility",
                "bank_user_notes",
                "bank_user_favorites",
                "user_notes",
                "app_users",
            }:
                cursor = conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            else:
                continue
            deleted[table] = int(cursor.rowcount if cursor.rowcount is not None else 0)
        conn.commit()
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset user solve/favorite data in tax_exam.db")
    parser.add_argument("--db-path", default="tax_exam.db")
    parser.add_argument("--user-id", default="")
    args = parser.parse_args(argv)

    if args.user_id.strip():
        result = reset_one_user(db_path=args.db_path, user_id=args.user_id.strip())
        out = {"scope": "single-user", "user_id": args.user_id.strip(), "deleted": result}
    else:
        result = reset_all_users(db_path=args.db_path)
        out = {"scope": "all-users", "deleted": result}

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
