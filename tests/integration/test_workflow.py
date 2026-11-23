import pytest

from src.domain.errors import ExtractionError, InvalidWorkflowTransition, SchemaValidationError
from src.domain.models import Stage
from src.storage.session_repository import SessionRepository


def test_lifecycle(reviewed):
    repo, wf, w = reviewed
    wf.validate(w)
    wf.exported(w)
    original = w.reports[0].model_dump_json()
    next_result = w.reports[0].extraction.model_copy(deep=True)
    next_result.actions.clear()
    wf.edit(w, next_result)
    assert w.stage == Stage.IN_REVIEW and len(w.reports) == 2
    assert w.reports[0].model_dump_json() == original
    assert repo.data.audit[-1].after is None
    wf.validate(w)
    clone = SessionRepository()
    clone.restore(repo.export_json())
    assert clone.data == repo.data


def test_changed_source_invalidates(reviewed):
    _, wf, w = reviewed
    wf.transcribe(w, "Une autre note.")
    assert not w.reports and w.stage == Stage.TRANSCRIBED
    with pytest.raises(InvalidWorkflowTransition):
        wf.validate(w)


def test_no_partial_result(session):
    _, wf, w, _, pipeline = session
    with pytest.raises(InvalidWorkflowTransition):
        wf.analyze(w, pipeline)
    wf.transcribe(w, "Nouvelle note de terrain.")
    wf.approve(w)
    with pytest.raises(ExtractionError):
        wf.analyze(w, pipeline)
    assert not w.reports and w.stage == Stage.TRANSCRIPT_APPROVED


def test_bad_source_blocks_validation(reviewed):
    _, wf, w = reviewed
    result = w.reports[-1].extraction.model_copy(deep=True)
    result.actions[0].source_excerpt = "Absent du texte"
    wf.edit(w, result)
    with pytest.raises(SchemaValidationError):
        wf.validate(w)
    result.actions.append(result.actions[0])
    with pytest.raises(SchemaValidationError):
        wf.edit(w, result)


def test_source_whitespace_and_revision_roundtrip(session):
    repo, wf, w, example, pipeline = session
    text = "  " + example.text + "\n"
    wf.transcribe(w, text)
    wf.approve(w)
    wf.analyze(w, pipeline)
    wf.validate(w)
    restored = SessionRepository()
    restored.restore(repo.export_json())
    assert restored.data.works[0].reports[0].source_text == text


def test_slow_analysis_cannot_publish_after_source_change(session):
    _, wf, w, example, pipeline = session
    wf.transcribe(w, example.text)
    wf.approve(w)

    class ConcurrentChange:
        def analyze(self, text, context, reference):
            wf.revise_text(w, "Une nouvelle version.")
            return pipeline.analyze(text, context, reference)

    with pytest.raises(InvalidWorkflowTransition):
        wf.analyze(w, ConcurrentChange())
    assert w.stage == Stage.TRANSCRIBED and not w.reports
