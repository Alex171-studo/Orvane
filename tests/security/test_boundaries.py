import json
from uuid import uuid4

import pytest

from src.config.settings import Settings
from src.domain.errors import (
    AudioValidationError,
    BudgetError,
    ProviderAuthenticationError,
    SchemaValidationError,
)
from src.providers.groq_transcription import GroqTranscriptionService
from src.providers.openai_extraction import OpenAIExtractionService
from src.providers.runtime import CallRuntime
from src.services.audio_service import validate_audio
from src.services.reporting_service import paragraph
from src.services.validation_service import integrity, materialize
from src.storage.session_repository import SessionRepository


@pytest.mark.parametrize(
    "name,data",
    [
        ("test.mp3", b"ID3" + bytes(7) + b"\xff\xfb\x90\x00audio"),
        ("recording.m4a", b"\x00\x00\x00\x14ftypM4A " + bytes(8) + b"mdat"),
        ("audio.ogg", b"OggS\x00" + bytes(24) + b"OpusHead"),
        ("audio.webm", b"\x1aE\xdf\xa3" + bytes(8) + b"webm"),
    ],
)
def test_container_identification(name, data):
    assert validate_audio(name, None, data, 1) == name.split(".")[1]
    with pytest.raises(AudioValidationError):
        validate_audio(name, None, b"unrelated content", 1)


def test_isolated_sessions(reviewed):
    repo, wf, w = reviewed
    fresh = SessionRepository()
    assert not fresh.data.projects and w.note.text.encode() not in fresh.export_json()
    wf.validate(w)
    assert not fresh.data.works
    assert paragraph("<script> &").text == "&lt;script&gt; &amp;"


@pytest.mark.parametrize(
    "mutation",
    [
        "broken_json",
        "size",
        "duplicate",
        "stage",
        "project",
        "source",
        "note",
        "revision",
        "citation",
    ],
)
def test_atomic_import(mutation, reviewed):
    repo, wf, w = reviewed
    wf.validate(w)
    before = repo.export_json()
    data = json.loads(before)
    work = data["works"][0]
    if mutation == "stage":
        work["stage"] = "IN_REVIEW"
    elif mutation == "project":
        work["note"]["project_id"] = str(uuid4())
    elif mutation == "source":
        work["note"]["text"] = "Autre transcription"
    elif mutation == "duplicate":
        data["projects"] *= 2
    elif mutation == "note":
        work["note"]["text"] = ""
    elif mutation == "revision":
        work["reports"][0]["revision"] = 9
    elif mutation == "citation":
        work["reports"][0]["extraction"]["actions"][0]["source_excerpt"] = "introuvable"
    blob = (
        b"{"
        if mutation == "broken_json"
        else b"x" * 12_000_001
        if mutation == "size"
        else json.dumps(data).encode()
    )
    with pytest.raises(SchemaValidationError):
        repo.restore(blob)
    assert repo.export_json() == before


def test_provider_guard():
    cfg = Settings()
    rt = CallRuntime(cfg)
    for cls in (GroqTranscriptionService, OpenAIExtractionService):
        with pytest.raises(ProviderAuthenticationError):
            cls(cfg, rt)
    with rt.lock, pytest.raises(BudgetError):
        rt.run("same", "Groq", "test", Exception, None)
    assert rt.spent == 0


def test_bad_links_and_semantic_mismatch(session):
    repo, _, w, example, _ = session
    proposal = example.proposal
    proposal.actions[0].assignee = "Thomas"
    proposal.actions[0].due_expression = "rapidement"
    result = materialize(proposal, example.text, w.reference_datetime.date())
    a = result.actions[0]
    assert a.requires_review and a.assignee is None and a.due_date is None and result.clarifications
    a.linked_issue_id = uuid4()
    with pytest.raises(SchemaValidationError):
        integrity(result, example.text)
    a.linked_issue_id = None
    result.clarifications[0].related_entity_id = uuid4()
    with pytest.raises(SchemaValidationError):
        integrity(result, example.text)
    proposal.actions[0].issue_index = 9
    with pytest.raises(SchemaValidationError):
        materialize(proposal, example.text, w.reference_datetime.date())
