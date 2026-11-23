from typing import Literal

from pydantic import Field, ValidationError

from src.domain.errors import SchemaValidationError
from src.domain.models import (
    AuditEvent,
    ExtractionResult,
    Model,
    ProcessingMetrics,
    Project,
    Stage,
    Work,
)
from src.services.validation_service import SECTIONS, integrity


class Archive(Model):
    version: Literal[1] = 1
    projects: list[Project] = Field(default_factory=list)
    works: list[Work] = Field(default_factory=list)
    audit: list[AuditEvent] = Field(default_factory=list)
    metrics: list[ProcessingMetrics] = Field(default_factory=list)


class SessionRepository:
    def __init__(self):
        self.data = Archive()

    def project(self, project_id):
        return next(p for p in self.data.projects if p.id == project_id)

    def work(self, note_id):
        return next(w for w in self.data.works if w.note.id == note_id)

    def event(self, entity_id, kind, before, after):
        self.data.audit.append(
            AuditEvent(entity_id=entity_id, event_type=kind, before=before, after=after)
        )

    def export_json(self):
        return self.data.model_dump_json(indent=2).encode()

    def restore(self, blob, max_chars=30000):
        if len(blob) > 12_000_000:
            raise SchemaValidationError("Archive trop volumineuse (12 Mo maximum).")
        try:
            archive = Archive.model_validate_json(blob)
            for event in archive.audit:
                if event.event_type == "proposed":
                    ExtractionResult.model_validate_json(event.after or "")
        except ValidationError:
            raise SchemaValidationError("L'archive ne respecte pas le format ORVANE.") from None
        projects = {p.id for p in archive.projects}
        ids = [p.id for p in archive.projects] + [w.note.id for w in archive.works]
        owners = {}
        for work in archive.works:
            if work.note.project_id not in projects or len(work.note.text) > max_chars:
                raise SchemaValidationError("Note ou chantier invalide.")
            if work.stage not in (Stage.NEW, Stage.TRANSCRIBED) and len(work.note.text.strip()) < 5:
                raise SchemaValidationError("Transcription manquante.")
            last = work.reports[-1] if work.reports else None
            in_review = work.stage in (Stage.ANALYZED, Stage.IN_REVIEW)
            if in_review != bool(last and last.status == "draft") or (
                work.stage in (Stage.VALIDATED, Stage.EXPORTED) and not last
            ):
                raise SchemaValidationError("État de révision incohérent.")
            for index, r in enumerate(work.reports, 1):
                ids.append(r.id)
                for section in SECTIONS:
                    for entity in getattr(r.extraction, section):
                        owner = owners.setdefault(entity.id, (r.note_id, section))
                        if owner != (r.note_id, section):
                            raise SchemaValidationError(
                                "Identifiant partagé entre des éléments distincts."
                            )
                if (
                    r.note_id != work.note.id
                    or r.project_id != work.note.project_id
                    or r.revision != index
                    or (r.status == "validated") != (r.validated_at is not None)
                    or (r.status == "draft" and r is not last)
                    or len(r.source_text) > max_chars
                ):
                    raise SchemaValidationError("Historique de révision incohérent.")
                integrity(r.extraction, r.source_text, enforce_sources=r.status == "validated")
            if (
                last
                and work.stage in (Stage.VALIDATED, Stage.EXPORTED, Stage.ANALYZED, Stage.IN_REVIEW)
                and last.source_text != work.note.text
            ):
                raise SchemaValidationError("La source de la révision ne correspond pas à la note.")
        if len(ids) != len(set(ids)):
            raise SchemaValidationError("Identifiants dupliqués dans l'archive.")
        self.data = archive
