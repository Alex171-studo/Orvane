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


def begin(app):
    go(app, 1)
    click(app, "Ouvrir la note")
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
    click(demo, "Charger la proposition")
    assert demo.error and work.stage == Stage.TRANSCRIPT_APPROVED


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


def test_auth_audio_analysis_and_rerun(monkeypatch):
    invitation = "offline-example-invitation-12345"
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("APP_ACCESS_TOKEN", invitation)
    monkeypatch.setenv("OPENAI_API_KEY", "offline")
    monkeypatch.setenv("GROQ_API_KEY", "offline")
    calls = []
    example = examples()[0]

    def transcribe(self, name, data, mime):
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
    next(x for x in app.radio if x.label == "2 · Source").set_value("Microphone").run()
    click(app, "Ouvrir la note")
    assert len(app.get("audio_input")) == 1
    next(x for x in app.radio if x.label == "Entrée audio").set_value("Fichier audio").run()
    next(f for f in app.file_uploader if f.label == "Importer un enregistrement").upload(
        "sample.wav", b"fixture", "audio/wav"
    ).run()
    app.run()
    assert not calls
    click(app, "Confirmer l’envoi à Groq")
    app.run()
    click(app, "Confirmer la transcription corrigée")
    app.run()
    assert calls == ["Groq"]
    click(app, "Confirmer l’analyse OpenAI")
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
