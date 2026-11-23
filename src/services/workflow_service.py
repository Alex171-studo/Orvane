from src.domain.errors import InvalidWorkflowTransition
from src.domain.models import Project, Report, SourceNote, Stage, Work, now
from src.services.validation_service import SECTIONS, integrity, prepare
from src.storage.base import Repository

TRANSITIONS = {
    Stage.NEW: {Stage.TRANSCRIBED},
    Stage.TRANSCRIBED: {Stage.TRANSCRIPT_APPROVED},
    Stage.TRANSCRIPT_APPROVED: {Stage.TRANSCRIBED, Stage.ANALYZED},
    Stage.ANALYZED: {Stage.IN_REVIEW, Stage.TRANSCRIBED},
    Stage.IN_REVIEW: {Stage.VALIDATED, Stage.TRANSCRIBED},
    Stage.VALIDATED: {Stage.EXPORTED, Stage.IN_REVIEW, Stage.TRANSCRIBED},
    Stage.EXPORTED: {Stage.IN_REVIEW, Stage.TRANSCRIBED},
}


class Workflow:
    def __init__(self, repo: Repository, settings):
        self.repo = repo
        self.cfg = settings

    def create(self, project: Project, reference, source_type):
        work = Work(
            note=SourceNote(project_id=project.id, text="", source_type=source_type),
            reference_datetime=reference,
        )
        self.repo.project(project.id)
        self.repo.data.works.append(work)
        self.repo.event(work.note.id, "created", None, source_type)
        return work

    def _require(self, w, *allowed):
        if w.stage not in allowed:
            raise InvalidWorkflowTransition("Cette opération est indisponible à cette étape.")

    def _move(self, w, target):
        if target not in TRANSITIONS[w.stage]:
            raise InvalidWorkflowTransition("Transition de compte rendu interdite.")
        self.repo.event(w.note.id, "stage", w.stage.value, target.value)
        w.stage = target

    def transcribe(self, w, text, metadata=None):
        prepare(text, self.cfg.MAX_TRANSCRIPT_CHARS)
        self.revise_text(w, text)
        if metadata is not None:
            w.transcription = metadata

    def revise_text(self, w, text):
        if len(text) > self.cfg.MAX_TRANSCRIPT_CHARS:
            prepare(text, self.cfg.MAX_TRANSCRIPT_CHARS)
        if text == w.note.text:
            return
        self.repo.event(w.note.id, "transcript", w.note.text, text)
        if w.reports and w.reports[-1].status == "draft":
            discarded = w.reports.pop()
            self.repo.event(discarded.id, "invalidated", discarded.model_dump_json(), None)
        w.note.text = text
        if w.stage != Stage.TRANSCRIBED:
            self._move(w, Stage.TRANSCRIBED)

    def approve(self, w):
        self._require(w, Stage.TRANSCRIBED)
        prepare(w.note.text, self.cfg.MAX_TRANSCRIPT_CHARS)
        self._move(w, Stage.TRANSCRIPT_APPROVED)

    def analyze(self, w, pipeline):
        self._require(w, Stage.TRANSCRIPT_APPROVED)
        approved_source = w.note.text
        result = pipeline.analyze(
            approved_source, self.repo.project(w.note.project_id), w.reference_datetime
        )
        self._require(w, Stage.TRANSCRIPT_APPROVED)
        if w.note.text != approved_source:
            raise InvalidWorkflowTransition("La source a changé pendant l’analyse.")
        report = Report(
            project_id=w.note.project_id,
            note_id=w.note.id,
            source_text=w.note.text,
            reference_datetime=w.reference_datetime,
            revision=len(w.reports) + 1,
            status="draft",
            validated_at=None,
            extraction=result,
        )
        w.reports.append(report)
        self.repo.event(report.id, "proposed", None, result.model_dump_json())
        self._move(w, Stage.ANALYZED)
        self._move(w, Stage.IN_REVIEW)
        return report

    def edit(self, w, result):
        self._require(w, Stage.IN_REVIEW, Stage.VALIDATED, Stage.EXPORTED)
        integrity(result, w.note.text, enforce_sources=False)
        old = w.reports[-1]
        if old.extraction == result:
            return old
        if old.status == "validated":
            draft = Report(
                project_id=old.project_id,
                note_id=old.note_id,
                source_text=old.source_text,
                reference_datetime=old.reference_datetime,
                revision=old.revision + 1,
                status="draft",
                validated_at=None,
                extraction=result,
            )
            w.reports.append(draft)
            self._move(w, Stage.IN_REVIEW)
        else:
            draft = old
        previous = old.extraction
        if result.summary != previous.summary:
            self.repo.event(draft.id, "summary_edit", previous.summary, result.summary)
        for section in SECTIONS:
            before = {i.id: i for i in getattr(previous, section)}
            after = {i.id: i for i in getattr(result, section)}
            for key in before.keys() | after.keys():
                a, b = before.get(key), after.get(key)
                if a != b:
                    self.repo.event(
                        key,
                        "entity_edit",
                        a.model_dump_json() if a else None,
                        b.model_dump_json() if b else None,
                    )
        draft.extraction = result.model_copy(deep=True)
        return draft

    def validate(self, w):
        self._require(w, Stage.IN_REVIEW)
        report = w.reports[-1]
        integrity(report.extraction, w.note.text)
        report.status = "validated"
        report.validated_at = now()
        self._move(w, Stage.VALIDATED)

    def exported(self, w):
        self._require(w, Stage.VALIDATED, Stage.EXPORTED)
        if w.stage == Stage.VALIDATED:
            self._move(w, Stage.EXPORTED)
