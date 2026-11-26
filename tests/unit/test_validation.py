from datetime import date

import pytest

from src.domain.errors import AudioValidationError, SchemaValidationError
from src.services.audio_service import validate_audio
from src.services.validation_service import prepare, resolve_date


@pytest.mark.parametrize(
    "value,day",
    [
        ("demain", 2),
        ("vendredi", 2),
        ("jeudi", None),
        ("dans 2 jours", 3),
        ("le 03/01/2026", 3),
        ("2026-01-04", 4),
        ("5 janvier 2026", 5),
        ("rapidement", None),
        ("31/02/2026", None),
        (None, None),
    ],
)
def test_deadline(value, day):
    result = resolve_date(value, date(2026, 1, 1))
    assert (result.day if result else None) == day


@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("../a.wav", None, b"0"),
        ("a.mp3", "audio/wav", b"x"),
        ("a.wav", None, b"RIFF"),
        ("a.mp3", None, b""),
        ("a.ogg", None, b"x" * 1000001),
    ],
)
def test_audio_reject(name, mime, data):
    with pytest.raises(AudioValidationError):
        validate_audio(name, mime, data, 1)


@pytest.mark.parametrize("text", ["", "a" * 21])
def test_note_limits(text):
    with pytest.raises(SchemaValidationError):
        prepare(text, 20)


def test_detach_removed_links(reviewed):
    from src.domain.models import Clarification
    from src.services.validation_service import detach_removed

    _, _, w = reviewed
    original = w.reports[0].extraction
    original.actions[0].linked_issue_id = original.issues[0].id
    original.clarifications.append(
        Clarification(
            question="Qui confirme ?",
            reason="À confirmer",
            source_excerpt=original.issues[0].source_excerpt,
            related_entity_id=original.issues[0].id,
        )
    )
    candidate = original.model_copy(deep=True)
    candidate.issues.clear()
    detach_removed(original, candidate)
    assert (
        candidate.actions[0].linked_issue_id is None
        and candidate.clarifications[0].related_entity_id is None
    )
    assert original.actions[0].linked_issue_id is not None


def test_date_is_not_substring_of_longer_deadline(session):
    from src.services.validation_service import materialize

    _, _, w, example, _ = session
    proposal = example.proposal
    proposal.actions[0].source_excerpt = "Karim doit appeler le loueur après-demain."
    result = materialize(proposal, proposal.actions[0].source_excerpt, w.reference_datetime.date())
    assert result.actions[0].due_date is None and result.clarifications
