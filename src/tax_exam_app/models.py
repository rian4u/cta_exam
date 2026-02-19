from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Confidence = Literal["high", "medium", "low"]
QuestionStatus = Literal["draft", "review_required", "published", "legal_hold"]
BatchMode = Literal["collect_only", "collect_and_process", "reprocess_existing"]


@dataclass(slots=True)
class CollectRequest:
    years: list[int]
    subjects: list[str]
    start_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RawQuestion:
    exam_year: int
    subject_code: str
    question_no: int
    raw_text: str
    source_url: str
    content_hash: str


@dataclass(slots=True)
class StructuredQuestion:
    exam_stage: str
    exam_year: int
    subject_code: str
    question_no: int
    question_text: str
    choices: list[str]
    answer_key: str

    def validate(self) -> None:
        if self.exam_stage != "1st":
            raise ValueError("exam_stage must be '1st'")
        if not self.question_text.strip():
            raise ValueError("question_text is required")
        if len(self.choices) < 4:
            raise ValueError("choices must contain at least 4 options")
        if self.answer_key not in {str(i) for i in range(1, len(self.choices) + 1)}:
            raise ValueError("answer_key must point to an existing choice")


@dataclass(slots=True)
class LegalRef:
    law_name: str
    article: str
    reference_url: str
    as_of_date: str


@dataclass(slots=True)
class UpdateDecision:
    needs_update: bool
    reason: str
    legal_refs: list[LegalRef]
    confidence: Confidence


@dataclass(slots=True)
class RevisedQuestion:
    structured: StructuredQuestion
    change_summary: str
    updated_flag: bool


@dataclass(slots=True)
class ExplanationResult:
    explanation_text: str
    needs_human_review: bool


@dataclass(slots=True)
class ValidationResult:
    status: QuestionStatus
    needs_human_review: bool
    validation_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProcessedQuestion:
    raw: RawQuestion
    structured: StructuredQuestion
    decision: UpdateDecision
    revised: RevisedQuestion
    explanation: ExplanationResult
    validation: ValidationResult


@dataclass(slots=True)
class NoteRecord:
    question_id: int
    state: Literal["wrong", "unsure", "bookmark", "review"]
    memo: str = ""
    tags: list[str] = field(default_factory=list)
    user_id: str = "local-user"
    source: Literal["local", "cloud"] = "local"


@dataclass(slots=True)
class BatchRunResult:
    batch_id: int
    status: Literal["running", "partial_success", "success", "failed"]
    counts: dict[str, int]
    finished_at: datetime
