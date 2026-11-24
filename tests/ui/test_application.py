import io
import wave
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.domain.models import Stage, Transcript
from src.providers.demo_provider import DATA, examples
from src.ui.pages import NAV

APP = Path(__file__).resolve().parents[2] / "app.py"


def button(app, label):
    return next(x for x in app.button if x.label == label)


def click(app, label):
    button(app, label).click().run()
    assert not app.exception


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    return AppTest.from_file(str(APP), default_timeout=20).run()


def go(app, index):
    app.radio(key="nav").set_value(NAV[index]).run()
    assert not app.exception


def source(app, value):
    next(r for r in app.radio if r.label == "2 · Source").set_value(value).run()


@pytest.fixture
def recording():
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "NONE"))
        wav.writeframes(bytes(640))
    return ("visite.wav", output.getvalue(), "audio/wav")


def begin(app):
    go(app, 1)
    source(app, "Note préenregistrée")
    click(app, "Ouvrir la note d’exemple")
    click(app, "Confirmer la transcription corrigée")
    click(app, "Charger la proposition")


def test_demo_end_to_end(demo):
    assert len(demo.session_state.repo.data.projects) == 5
    begin(demo)
    synthesis = next(x for x in demo.text_area if x.label == "Synthèse opérationnelle")
    synthesis.set_value("Synthèse revue par le conducteur.")
    click(demo, "Enregistrer les modifications")
    click(demo, "Valider le compte rendu")
    w = demo.session_state.repo.data.works[0]
    assert w.stage == Stage.VALIDATED and w.reports[0].extraction.summary.startswith(
        "Synthèse revue"
    )
    for i in [2, 3, 4, 0]:
        go(demo, i)
    assert any("Rapports validés</dt><dd>1</dd>" in node.proto.body for node in demo.get("html"))
    assert not demo.session_state.repo.data.metrics and not demo.session_state.runtime.spent


def test_change_invalidates_immediately(demo):
    begin(demo)
    demo.text_area[0].set_value("Nouvelle note corrigée.").run()
    work = demo.session_state.repo.data.works[0]
    assert work.stage == Stage.TRANSCRIBED and not work.reports
    click(demo, "Confirmer la transcription corrigée")
    assert "Charger la proposition" not in [b.label for b in demo.button]
    assert work.stage == Stage.TRANSCRIPT_APPROVED


def test_archive_reset_import(demo):
    begin(demo)
    click(demo, "Valider le compte rendu")
    archive = demo.session_state.repo.export_json()
    demo.session_state.runtime.spent = 3
    demo.checkbox[0].check().run()
    click(demo, "Réinitialiser")
    assert not demo.session_state.repo.data.works and demo.session_state.runtime.spent == 3
    demo.file_uploader(key="archive").upload("session.json", archive, "application/json").run()
    click(demo, "Remplacer par l’archive")
    assert demo.session_state.repo.data.works[0].stage == Stage.VALIDATED
    assert demo.session_state.runtime.spent == 3


def test_auth_audio_analysis_and_rerun(monkeypatch, recording):
    invitation = "offline-example-invitation-12345"
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("APP_ACCESS_TOKEN", invitation)
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setenv("GROQ_API_KEY", "offline")
    calls = []
    example = examples()[0]

    def transcribe(self, name, data, mime=None):
        assert data == recording[1]
        calls.append("Groq")
        return Transcript(text=example.text, language=None, duration=None, segments=None)

    def extract(self, source, context, reference):
        calls.append("OpenAI")
        return example.proposal

    monkeypatch.setattr(
        "src.providers.groq_transcription.GroqTranscriptionService.transcribe", transcribe
    )
    monkeypatch.setattr("src.providers.openai_extraction.OpenAIExtractionService.extract", extract)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.radio
    app.text_input[0].set_value("wrong")
    click(app, "Accéder à ORVANE")
    assert app.error
    app.text_input[0].set_value(invitation)
    click(app, "Accéder à ORVANE")
    go(app, 1)
    app.text_input[0].set_value(example.name)
    app.text_input[1].set_value(example.location)
    click(app, "Créer le chantier")
    source(app, "Microphone")
    assert len(app.audio_input) == 1
    source(app, "Fichier audio")
    next(f for f in app.file_uploader if f.label == "Importer un enregistrement").upload(
        *recording
    ).run()
    click(app, "Enregistrer le vocal")
    app.run()
    assert not calls
    click(app, "Transcrire le vocal")
    app.run()
    click(app, "Confirmer la transcription corrigée")
    app.run()
    assert calls == ["Groq"]
    click(app, "Analyser la note")
    app.run()
    assert calls == ["Groq", "OpenAI"]


def test_quality_upload(demo):
    go(demo, 4)
    next(x for x in demo.file_uploader if x.label.startswith("Rapport")).upload(
        "eval.json", (DATA / "evaluation/replay_report.json").read_bytes(), "application/json"
    ).run()
    assert not demo.exception and demo.dataframe


def test_action_plan_edit_creates_pending_revision(demo):
    begin(demo)
    click(demo, "Valider le compte rendu")
    go(demo, 2)
    work = demo.session_state.repo.data.works[0]
    key = f"plan-None-{len(demo.session_state.repo.data.audit)}-actions"
    demo.session_state[key] = {
        "edited_rows": {0: {"status": "Terminée"}},
        "added_rows": [],
        "deleted_rows": [],
    }
    click(demo, "Enregistrer le suivi")
    assert work.stage == Stage.IN_REVIEW
    assert work.reports[0].extraction.actions[0].status.value == "À faire"
    assert work.reports[1].extraction.actions[0].status.value == "Terminée"
    go(demo, 3)
    click(demo, "Valider le compte rendu")
    go(demo, 0)
    assert any("Actions ouvertes</dt><dd>0</dd>" in node.proto.body for node in demo.get("html"))


def test_review_add_then_delete_action(demo):
    begin(demo)
    repo = demo.session_state.repo
    work = repo.data.works[0]
    report = work.reports[0]

    def key():
        return f"review-{report.id}-{len(repo.data.audit)}actions"

    added = {
        "description": "Confirmer le maintien de l’accès",
        "source_excerpt": report.extraction.decisions[0].source_excerpt,
        "requires_review": True,
        "status": "À faire",
    }
    demo.session_state[key()] = {"edited_rows": {}, "added_rows": [added], "deleted_rows": []}
    click(demo, "Enregistrer les modifications")
    assert len(report.extraction.actions) == 2 and report.extraction.actions[1].assignee is None
    demo.session_state[key()] = {"edited_rows": {}, "added_rows": [], "deleted_rows": [0]}
    click(demo, "Enregistrer les modifications")
    assert [a.description for a in report.extraction.actions] == [added["description"]]
    assert repo.data.audit[-1].event_type == "entity_edit" and repo.data.audit[-1].after is None


def test_personal_note_without_keys(demo):
    go(demo, 1)
    demo.text_input[0].set_value("Mon chantier")
    demo.text_input[1].set_value("Rouen")
    click(demo, "Créer le chantier")
    project = demo.session_state.repo.data.projects[-1]
    assert demo.selectbox(key="capture_project").value == project.id
    assert next(r for r in demo.radio if r.label == "2 · Source").value == "Texte"
    demo.text_area[0].set_value("La pompe arrive mercredi.").run()
    click(demo, "Enregistrer la note")
    click(demo, "Confirmer la transcription corrigée")
    w = demo.session_state.repo.data.works[0]
    assert w.note.project_id == project.id and w.note.text == "La pompe arrive mercredi."
    assert w.note.source_type == "text" and not w.reports and demo.session_state.runtime.spent == 0
    assert button(demo, "Analyser la note").disabled
    assert not demo.info


@pytest.mark.parametrize("method", ["Microphone", "Fichier audio"])
def test_personal_recording_without_keys(demo, recording, method):
    go(demo, 1)
    source(demo, method)
    widget = (
        demo.audio_input[0]
        if method == "Microphone"
        else next(f for f in demo.file_uploader if f.label == "Importer un enregistrement")
    )
    widget.upload(*recording).run()
    assert not demo.session_state.repo.data.works
    click(demo, "Enregistrer le vocal")
    w = demo.session_state.repo.data.works[0]
    assert demo.session_state.recordings[w.note.id] == ("wav", recording[1])
    assert button(demo, "Transcrire le vocal").disabled
    assert not demo.info
    go(demo, 0)
    go(demo, 1)
    demo.selectbox(key="working_note").set_value(w.note.id).run()
    assert any(box.label == "Réécouter le vocal" for box in demo.checkbox)
    demo.text_area[0].set_value("La visite est terminée.").run()
    click(demo, "Confirmer la transcription corrigée")
    assert w.stage == Stage.TRANSCRIPT_APPROVED and not demo.session_state.runtime.spent
    assert not AppTest.from_file(str(APP), default_timeout=20).run().session_state.repo.data.works


def test_invalid_upload_does_not_create_note(demo):
    go(demo, 1)
    source(demo, "Fichier audio")
    next(f for f in demo.file_uploader if f.label == "Importer un enregistrement").upload(
        "faux.wav", b"not audio", "audio/wav"
    ).run()
    click(demo, "Enregistrer le vocal")
    assert demo.error and not demo.session_state.repo.data.works


def test_unlock_saved_recording_with_configured_groq(monkeypatch, recording):
    token = "session-test-invitation-of-at-least-24-chars"
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("APP_ACCESS_TOKEN", token)
    monkeypatch.setenv("GROQ_API_KEY", "offline")
    calls = []

    def transcribe(self, name, data, mime=None):
        calls.append(data)
        return Transcript(text="La pompe est arrivée.", language="fr", duration=None, segments=None)

    monkeypatch.setattr(
        "src.providers.groq_transcription.GroqTranscriptionService.transcribe", transcribe
    )
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    go(app, 1)
    source(app, "Microphone")
    app.audio_input[0].upload(*recording).run()
    click(app, "Enregistrer le vocal")
    work = app.session_state.repo.data.works[0]
    assert all(str(work.note.id)[:6] not in node.value for node in app.text)
    assert not app.info
    app.text_input[0].set_value("faux")
    click(app, "Accéder à ORVANE")
    assert app.error and not calls
    app.text_input[0].set_value(token)
    click(app, "Accéder à ORVANE")
    assert not calls and work.stage == Stage.NEW
    click(app, "Transcrire le vocal")
    app.run()
    assert calls == [recording[1]]
    assert work.stage == Stage.TRANSCRIBED
    assert app.text_area[0].value == "La pompe est arrivée."


def test_short_invitation_never_unlocks_provider(monkeypatch, recording):
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "test")
    monkeypatch.setenv("GROQ_API_KEY", "offline")
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    go(app, 1)
    source(app, "Microphone")
    app.audio_input[0].upload(*recording).run()
    click(app, "Enregistrer le vocal")
    assert button(app, "Transcrire le vocal").disabled
    assert not app.info and not app.session_state.runtime.spent
