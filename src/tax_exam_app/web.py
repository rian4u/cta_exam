import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .models import CollectRequest, NoteRecord
from .repository import SQLiteRepository

try:
    from .pipeline import BatchPipeline
except ModuleNotFoundError:
    BatchPipeline = None


def _normalize_answer(value: str | None) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split()).strip()
    if not text:
        return ""

    text = re.sub(r"\(?\s*\d+\s*-\s*\d+\s*\)?\s*$", "", text).strip()
    text = re.split(r"\b20\d{2}\s*년도\b", text, maxsplit=1)[0].strip()

    if text and text[0] in {"1", "2", "3", "4", "5"}:
        return text[0]
    return text


class BatchRequest(BaseModel):
    mode: str = Field(default="collect_and_process")
    years: str = Field(default="2024-2025")
    subjects: str = Field(default="TAX_LAW_1")
    start_urls: list[str] = Field(default_factory=list)


class NoteRequest(BaseModel):
    question_id: int
    state: str
    memo: str = ""
    tags: list[str] = Field(default_factory=list)
    user_id: str = "local-user"
    source: str = "local"


class MockSubmitRequest(BaseModel):
    exam_year: int
    subject_code: str
    answers: dict[int, str] = Field(default_factory=dict)
    user_id: str = "local-user"
    started_at: str | None = None
    duration_seconds: int = 0


class BankNoteRequest(BaseModel):
    exam_year: int
    subject_code: str
    question_no_exam: int
    state: str = "wrong"
    memo: str = ""
    tags: list[str] = Field(default_factory=list)
    user_id: str = "local-user"
    source: str = "mock"


class BankNoteDeleteRequest(BaseModel):
    exam_year: int
    subject_code: str
    question_no_exam: int
    user_id: str = "local-user"
    state_prefix: str | None = None


class OXSubmitRequest(BaseModel):
    subject_code: str
    answers: dict[int, str] = Field(default_factory=dict)
    user_id: str = "local-user"
    started_at: str | None = None
    duration_seconds: int = 0


class FavoriteRequest(BaseModel):
    exam_year: int
    subject_code: str
    question_no_exam: int
    color: str
    memo: str = ""
    tags: list[str] = Field(default_factory=list)
    user_id: str = "local-user"
    source: str = "mock"


class FavoriteDeleteRequest(BaseModel):
    exam_year: int
    subject_code: str
    question_no_exam: int
    user_id: str = "local-user"


class UserUpsertRequest(BaseModel):
    user_id: str
    display_name: str | None = None


class ChoiceVisibilityRequest(BaseModel):
    user_id: str = "local-user"
    exam_year: int
    subject_code: str
    question_no_exam: int
    choice_no: int
    hidden: bool = True


def _parse_years(expr: str) -> list[int]:
    if "-" in expr:
        s, e = expr.split("-", 1)
        return list(range(int(s), int(e) + 1))
    return [int(x.strip()) for x in expr.split(",") if x.strip()]


def _parse_subjects(expr: str) -> list[str]:
    return [x.strip() for x in expr.split(",") if x.strip()]


def create_app(db_path: str = "./tax_exam.db") -> FastAPI:
    app = FastAPI(title="세무사 돌돌이", version="0.2.0")
    repo = SQLiteRepository(db_path)
    pipeline = BatchPipeline(repo) if BatchPipeline is not None else None

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/users/upsert")
    def upsert_user(req: UserUpsertRequest) -> dict:
        repo.ensure_user(user_id=req.user_id, display_name=req.display_name)
        return {"ok": True}

    @app.get("/api/users/{user_id}/subject-recent-scores")
    def user_subject_recent_scores(user_id: str) -> list[dict]:
        return repo.list_user_subject_recent_scores(user_id=user_id)

    @app.get("/api/dashboard/learning-metrics")
    def dashboard_learning_metrics(user_id: str = "local-user") -> dict:
        return repo.get_learning_dashboard_scores(user_id=user_id)

    @app.get("/api/choice-visibility")
    def get_choice_visibility(
        user_id: str = "local-user",
        exam_year: int = Query(..., ge=1900, le=2100),
        subject_code: str = Query(..., min_length=1),
    ) -> list[dict]:
        return repo.get_choice_visibility(user_id=user_id, exam_year=exam_year, subject_code=subject_code)

    @app.post("/api/choice-visibility")
    def set_choice_visibility(req: ChoiceVisibilityRequest) -> dict:
        repo.set_choice_visibility(
            user_id=req.user_id,
            exam_year=req.exam_year,
            subject_code=req.subject_code,
            question_no_exam=req.question_no_exam,
            choice_no=req.choice_no,
            hidden=req.hidden,
        )
        return {"ok": True}

    @app.post("/api/batch/run")
    def run_batch(req: BatchRequest) -> dict:
        if pipeline is None:
            raise HTTPException(status_code=503, detail="Batch pipeline is disabled in this deployment")
        request = CollectRequest(
            years=_parse_years(req.years),
            subjects=_parse_subjects(req.subjects),
            start_urls=req.start_urls,
        )
        result = pipeline.run(req.mode, request)
        return {
            "batch_id": result.batch_id,
            "status": result.status,
            "counts": result.counts,
            "finished_at": result.finished_at.isoformat(),
        }

    @app.get("/api/batches")
    def list_batches(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
        return repo.list_batch_runs(limit=limit)

    @app.get("/api/questions")
    def list_questions(
        limit: int = Query(default=50, ge=1, le=200),
        status: str | None = None,
        subject_code: str | None = None,
        exam_year: int | None = None,
    ) -> list[dict]:
        return repo.list_questions(limit=limit, status=status, subject_code=subject_code, exam_year=exam_year)

    @app.get("/api/questions/{question_id}")
    def get_question(question_id: int) -> dict:
        question = repo.get_question(question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        return question

    @app.post("/api/notes")
    def upsert_note(req: NoteRequest) -> dict:
        note = NoteRecord(
            question_id=req.question_id,
            state=req.state,
            memo=req.memo,
            tags=req.tags,
            user_id=req.user_id,
            source=req.source,
        )
        repo.upsert_note(note)
        return {"ok": True}

    @app.get("/api/notes")
    def list_notes(user_id: str = "local-user") -> list[dict]:
        return repo.list_notes(user_id=user_id)

    @app.post("/api/bank-notes")
    def upsert_bank_note(req: BankNoteRequest) -> dict:
        repo.upsert_bank_note(
            user_id=req.user_id,
            exam_year=req.exam_year,
            subject_code=req.subject_code,
            question_no_exam=req.question_no_exam,
            state=req.state,
            memo=req.memo,
            tags=req.tags,
            source=req.source,
        )
        return {"ok": True}

    @app.get("/api/bank-notes")
    def list_bank_notes(
        user_id: str = "local-user",
        exam_year: int | None = None,
        subject_code: str | None = None,
    ) -> list[dict]:
        return repo.list_bank_notes(user_id=user_id, exam_year=exam_year, subject_code=subject_code)

    @app.post("/api/bank-notes/delete")
    def delete_bank_note(req: BankNoteDeleteRequest) -> dict:
        deleted = repo.delete_bank_note(
            user_id=req.user_id,
            exam_year=req.exam_year,
            subject_code=req.subject_code,
            question_no_exam=req.question_no_exam,
            state_prefix=req.state_prefix,
        )
        return {"ok": True, "deleted": deleted}

    @app.post("/api/favorites")
    def upsert_favorite(req: FavoriteRequest) -> dict:
        repo.upsert_bank_favorite(
            user_id=req.user_id,
            exam_year=req.exam_year,
            subject_code=req.subject_code,
            question_no_exam=req.question_no_exam,
            color=req.color,
            memo=req.memo,
            tags=req.tags,
            source=req.source,
        )
        return {"ok": True}

    @app.post("/api/favorites/delete")
    def delete_favorite(req: FavoriteDeleteRequest) -> dict:
        deleted = repo.delete_bank_favorite(
            user_id=req.user_id,
            exam_year=req.exam_year,
            subject_code=req.subject_code,
            question_no_exam=req.question_no_exam,
        )
        return {"ok": True, "deleted": deleted}

    @app.get("/api/stats")
    def stats() -> dict:
        return repo.get_dashboard_stats()

    @app.get("/api/mock/options")
    def mock_options() -> list[dict]:
        options = repo.list_mock_options()
        return [item for item in options if item["answered_questions"] >= item["total_questions"] and item["total_questions"] > 0]

    @app.get("/api/mock/questions")
    def mock_questions(exam_year: int, subject_code: str) -> list[dict]:
        questions = repo.get_mock_questions(exam_year=exam_year, subject_code=subject_code)
        if not questions:
            raise HTTPException(status_code=404, detail="Mock questions not found")
        redacted: list[dict] = []
        for question in questions:
            copied = dict(question)
            copied.pop("service_answer", None)
            copied.pop("explanation_text", None)
            redacted.append(copied)
        return redacted

    @app.get("/api/mock/user-stats")
    def mock_user_stats(
        user_id: str = "local-user",
        exam_year: int = Query(..., ge=1900, le=2100),
        subject_code: str = Query(..., min_length=1),
    ) -> list[dict]:
        return repo.get_user_mock_question_stats(user_id=user_id, exam_year=exam_year, subject_code=subject_code)

    @app.get("/api/mock/explanation/{question_id}")
    def mock_question_explanation(question_id: int) -> dict:
        row = repo.get_bank_question_explanation(question_id=question_id)
        if not row:
            raise HTTPException(status_code=404, detail="Question not found")
        row["correct_answer"] = _normalize_answer(row["correct_answer"])
        return row

    @app.post("/api/mock/submit")
    def mock_submit(req: MockSubmitRequest) -> dict:
        questions = repo.get_mock_questions(exam_year=req.exam_year, subject_code=req.subject_code)
        if not questions:
            raise HTTPException(status_code=404, detail="Mock questions not found")

        total = len(questions)
        answered = 0
        correct = 0
        details: list[dict] = []
        for question in questions:
            qid = question["id"]
            chosen = (req.answers.get(qid) or "").strip()
            official = _normalize_answer(question["service_answer"])
            is_correct = bool(chosen) and (chosen == official)
            if chosen:
                answered += 1
            if is_correct:
                correct += 1
            details.append(
                {
                    "question_id": qid,
                    "exam_year": req.exam_year,
                    "subject_code": req.subject_code,
                    "question_no_exam": question["question_no_exam"],
                    "subject_name": question["subject_name"],
                    "question_text": question["question_text"],
                    "choices": question["choices"],
                    "selected_answer": chosen,
                    "correct_answer": official,
                    "is_correct": is_correct,
                    "explanation_text": question["explanation_text"],
                }
            )

        score_percent = round((correct / total) * 100, 2) if total else 0.0
        score_100 = round((correct / total) * 100, 1) if total else 0.0
        attempt_id = repo.record_exam_attempt(
            user_id=req.user_id,
            mode="mock",
            exam_year=req.exam_year,
            subject_code=req.subject_code,
            total_questions=total,
            answered_questions=answered,
            correct_count=correct,
            score_100=score_100,
            details=details,
            started_at=req.started_at,
            duration_seconds=req.duration_seconds,
        )

        return {
            "exam_year": req.exam_year,
            "subject_code": req.subject_code,
            "attempt_id": attempt_id,
            "total_questions": total,
            "answered_questions": answered,
            "correct_count": correct,
            "score_percent": score_percent,
            "score_100": score_100,
            "details": details,
        }

    @app.get("/api/ox/questions")
    def ox_questions(exam_year: int, subject_code: str) -> list[dict]:
        rows = repo.get_ox_candidates(exam_year=exam_year, subject_code=subject_code)
        if not rows:
            raise HTTPException(status_code=404, detail="OX candidates not found")
        return rows

    @app.get("/api/ox/options")
    def ox_options() -> list[dict]:
        return repo.list_ox_subject_options()

    @app.get("/api/ox/questions/v2")
    def ox_questions_v2(subject_code: str) -> list[dict]:
        rows = repo.get_ox_questions(subject_code=subject_code)
        if not rows:
            raise HTTPException(status_code=404, detail="OX questions not found")
        return rows

    @app.get("/api/ox/user-stats")
    def ox_user_stats(user_id: str = "local-user", subject_code: str = Query(..., min_length=1)) -> list[dict]:
        return repo.get_user_ox_item_stats(user_id=user_id, subject_code=subject_code)

    @app.post("/api/ox/submit")
    def ox_submit(req: OXSubmitRequest) -> dict:
        questions = repo.get_ox_questions(subject_code=req.subject_code)
        if not questions:
            raise HTTPException(status_code=404, detail="OX questions not found")

        total = len(questions)
        answered = 0
        correct = 0
        details: list[dict] = []
        for question in questions:
            qid = question["id"]
            expected = (question["expected_ox"] or "").strip().upper()
            chosen = (req.answers.get(qid) or "").strip().upper()
            is_correct = bool(chosen) and expected and (chosen == expected)
            if chosen:
                answered += 1
            if is_correct:
                correct += 1
            details.append(
                {
                    "id": qid,
                    "exam_year": question["exam_year"],
                    "subject_code": question["subject_code"],
                    "question_no_exam": question["question_no_exam"],
                    "choice_no": question["choice_no"],
                    "selected_ox": chosen,
                    "expected_ox": expected,
                    "is_correct": is_correct,
                    "choice_text": question["choice_text"],
                    "choice_explanation_text": question.get("choice_explanation_text", ""),
                    "judge_reason": question.get("judge_reason", ""),
                }
            )

        score_percent = round((correct / total) * 100, 2) if total else 0.0
        score_100 = round((correct / total) * 100, 1) if total else 0.0
        attempt_id = repo.record_exam_attempt(
            user_id=req.user_id,
            mode="ox",
            exam_year=None,
            subject_code=req.subject_code,
            total_questions=total,
            answered_questions=answered,
            correct_count=correct,
            score_100=score_100,
            details=details,
            started_at=req.started_at,
            duration_seconds=req.duration_seconds,
        )

        return {
            "subject_code": req.subject_code,
            "attempt_id": attempt_id,
            "total_questions": total,
            "answered_questions": answered,
            "correct_count": correct,
            "score_percent": score_percent,
            "score_100": score_100,
            "details": details,
        }

    return app


app = create_app()
