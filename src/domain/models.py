from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Index = Annotated[int, Field(ge=0)]


def now():
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Stage(StrEnum):
    NEW = "NEW"
    TRANSCRIBED = "TRANSCRIBED"
    TRANSCRIPT_APPROVED = "TRANSCRIPT_APPROVED"
    ANALYZED = "ANALYZED"
    IN_REVIEW = "IN_REVIEW"
    VALIDATED = "VALIDATED"
    EXPORTED = "EXPORTED"


class Priority(StrEnum):
    LOW = "Basse"
    NORMAL = "Normale"
    HIGH = "Haute"


class Severity(StrEnum):
    LOW = "Mineure"
    MAJOR = "Majeure"
    CRITICAL = "Critique"


class Status(StrEnum):
    TODO = "À faire"
    ACTIVE = "En cours"
    DONE = "Terminée"


class WorkStatus(StrEnum):
    PLANNED = "Planifié"
    ACTIVE = "En cours"
    DONE = "Terminé"
    UNKNOWN = "Non précisé"


class ProjectContext(Model):
    name: Text
    location: Text
    reference_timezone: str

    @field_validator("reference_timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Fuseau horaire inconnu.") from None
        return value


class Project(ProjectContext):
    id: UUID = Field(default_factory=uuid4)


class SourceNote(Model):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    text: str
    source_type: Literal["text", "audio", "demo"]
    created_at: AwareDatetime = Field(default_factory=now)


class Evidence(Model):
    source_excerpt: Text
    requires_review: bool


class ObservationFields(Evidence):
    description: Text
    category: Literal["Avancement", "Observation", "Risque"]
    work_status: WorkStatus


class IssueFields(Evidence):
    title: Text
    description: Text
    severity: Severity | None
    operational_impact: Text | None


class ActionFields(Evidence):
    description: Text
    assignee: Text | None
    priority: Priority | None
    status: Status


class DecisionFields(Evidence):
    description: Text


class ClarificationFields(Model):
    question: Text
    reason: Text
    source_excerpt: Text


class ProposedAction(ActionFields):
    due_expression: Text | None
    issue_index: Index | None


class ProposedClarification(ClarificationFields):
    action_index: Index | None


class Proposal(Model):
    summary: Text
    observations: list[ObservationFields]
    issues: list[IssueFields]
    actions: list[ProposedAction]
    decisions: list[DecisionFields]
    clarifications: list[ProposedClarification]


class Entity(Model):
    id: UUID = Field(default_factory=uuid4)


class Observation(ObservationFields, Entity):
    pass


class Issue(IssueFields, Entity):
    is_open: bool = True


class Decision(DecisionFields, Entity):
    pass


class ActionItem(ActionFields, Entity):
    due_date: date | None
    linked_issue_id: UUID | None


class Clarification(ClarificationFields, Entity):
    related_entity_id: UUID | None


class ExtractionResult(Model):
    summary: Text
    observations: list[Observation]
    issues: list[Issue]
    actions: list[ActionItem]
    decisions: list[Decision]
    clarifications: list[Clarification]


class Report(Entity):
    project_id: UUID
    note_id: UUID
    source_text: Annotated[str, Field(min_length=1)]
    reference_datetime: AwareDatetime | None = None
    revision: Annotated[int, Field(ge=1)]
    status: Literal["draft", "validated"]
    extraction: ExtractionResult
    validated_at: AwareDatetime | None
    created_at: AwareDatetime = Field(default_factory=now)


class ProcessingMetrics(Entity):
    provider: Literal["Groq", "OpenAI"]
    model: str
    request_id: str | None = None
    started_at: AwareDatetime = Field(default_factory=now)
    duration_ms: Annotated[float, Field(ge=0)] = 0.0
    input_tokens: Index | None = None
    output_tokens: Index | None = None
    error_type: str | None = None


class AuditEvent(Entity):
    entity_id: UUID
    event_type: str
    before: str | None
    after: str | None
    timestamp: AwareDatetime = Field(default_factory=now)


class Segment(Model):
    start: float | None
    end: float | None
    text: str | None


class Transcript(Model):
    text: Text
    language: str | None
    duration: float | None
    segments: list[Segment] | None


class Work(Model):
    note: SourceNote
    reference_datetime: AwareDatetime
    stage: Stage = Stage.NEW
    transcription: Transcript | None = None
    reports: list[Report] = Field(default_factory=list)
