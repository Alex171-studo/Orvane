import io
import wave
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.domain.errors import ExtractionError
from src.domain.models import Stage, Transcript

APP = Path(__file__).resolve().parents[2] / "app.py"
GENERATE = "Confirmer et générer le compte rendu"


def button(app, label):
    return next(x for x in app.button if x.label == label)


def click(app, label):
    button(app, label).click().run()
    assert not app.exception


def start():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    return app


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "abcd")


@pytest.fixture
def recording():
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "NONE"))
        wav.writeframes(bytes(640))
    return ("visite.wav", output.getvalue(), "audio/wav")


@pytest.fixture
def extraction(monkeypatch, session):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test")
    sample = session[3]
    calls = []

    def extract(self, source, context, reference):
        calls.append(source)
        return sample.proposal

    monkeypatch.setattr("src.providers.openai_extraction.OpenAIExtractionService.extract", extract)
    return sample, calls


def enter(app, text):
    app.text_input[0].set_value("Résidence Horizon")
    app.text_area[0].set_value(text).run()


def test_blank_workspace_and_archive():
    app = start()
    assert not app.session_state.repo.data.projects
    assert app.text_area[0].value == app.text_input[0].value == ""
    enter(app, "La visite est terminée.")
    assert button(app, GENERATE).disabled
    click(app, "Enregistrer la note")
    repo = app.session_state.repo
    assert len(repo.data.works) == 1
    archive = repo.export_json()
    app.session_state.runtime.spent = 3
    app.checkbox[0].check().run()
    click(app, "Effacer la session")
    assert not app.session_state.repo.data.works and app.session_state.runtime.spent == 3
    app.file_uploader(key="archive").upload("session.json", archive, "application/json").run()
    click(app, "Remplacer la session par l’archive")
    click(app, next(x.label for x in app.button if x.label.startswith("Résidence Horizon")))
    assert app.text_area[0].value == "La visite est terminée."
    click(app, "Nouvelle note")
    assert not app.text_area[0].value
    assert len(app.session_state.repo.data.projects) == 1


@pytest.mark.parametrize("source", ["Microphone", "Fichier audio"])
def test_audio_to_validated_pdf(monkeypatch, extraction, recording, source):
    sample, calls = extraction
    monkeypatch.setenv("GROQ_API_KEY", "offline")
    monkeypatch.setenv("APP_MODE", "demo")

    def transcribe(self, filename, data, mime):
        assert data == recording[1] and mime == recording[2]
        calls.append("audio")
        return Transcript(text=sample.text, language=None, duration=None, segments=None)

    monkeypatch.setattr(
        "src.providers.groq_transcription.GroqTranscriptionService.transcribe", transcribe
    )
    app = start()
    app.radio[0].set_value(source).run()
    widget = app.audio_input[0] if source == "Microphone" else app.file_uploader(key="capture-file")
    widget.upload(*recording).run()
    assert not calls and not app.text_area
    click(app, "Transcrire le vocal")
    app.run()
    assert calls == ["audio"] and app.text_area[0].value == sample.text
    corrected = sample.text + " La visite est close."
    app.text_area[0].set_value(corrected).run()
    click(app, GENERATE)
    app.run()
    assert calls == ["audio", corrected]
    work = app.session_state.repo.data.works[0]
    assert work.stage == Stage.IN_REVIEW and work.transcription.text == sample.text
    assert not any("PDF" in x.label for x in app.get("download_button"))
    app.text_area[1].set_value("Synthèse relue sur place.")
    click(app, "Valider le compte rendu")
    assert (
        work.stage == Stage.VALIDATED
        and work.reports[0].extraction.summary == "Synthèse relue sur place."
    )
    assert any("PDF validé" in x.label for x in app.get("download_button"))
    assert calls == ["audio", corrected]


def test_write_edit_revision(extraction):
    sample, calls = extraction
    app = start()
    enter(app, sample.text)
    click(app, GENERATE)
    repo = app.session_state.repo
    work = repo.data.works[0]
    click(app, "Valider le compte rendu")

    app.toggle[0].set_value(True).run()

    def edit_action(edited=None, added=None, deleted=None):
        key = f"review-{work.reports[-1].id}-{len(repo.data.audit)}actions"
        app.session_state[key] = {
            "edited_rows": edited or {},
            "added_rows": added or [],
            "deleted_rows": deleted or [],
        }
        click(app, "Enregistrer les modifications")

    edit_action({0: {"status": "Terminée"}})
    assert work.stage == Stage.IN_REVIEW and len(work.reports) == 2
    assert work.reports[0].extraction.actions[0].status == "À faire"
    assert work.reports[1].extraction.actions[0].status == "Terminée"
    added = {
        "description": "Prévenir le responsable",
        "source_excerpt": sample.proposal.actions[0].source_excerpt,
        "requires_review": True,
        "status": "À faire",
    }
    edit_action(added=[added])
    assert len(work.reports[-1].extraction.actions) == 2
    edit_action(deleted=[0])
    assert work.reports[-1].extraction.actions[0].description == added["description"]
    click(app, "Valider le compte rendu")
    assert len(app.selectbox[0].options) == 2
    app.text_area[0].set_value("Une autre note.").run()
    assert work.stage == Stage.TRANSCRIBED and work.reports[-1].source_text == sample.text
    assert calls == [sample.text]


def test_provider_failure_retry_and_source_change(monkeypatch, extraction):
    sample, _ = extraction
    attempts = []

    def extract(self, source, context, reference):
        attempts.append(source)
        if len(attempts) == 1:
            raise ExtractionError("Service indisponible.")
        return sample.proposal

    monkeypatch.setattr("src.providers.openai_extraction.OpenAIExtractionService.extract", extract)
    app = start()
    enter(app, sample.text)
    click(app, GENERATE)
    assert app.error and app.text_area[0].value == sample.text
    app.run()
    assert len(attempts) == 1
    click(app, GENERATE)
    (work,) = app.session_state.repo.data.works
    assert len(work.reports) == 1
    app.text_area[0].set_value("La livraison arrive.").run()
    assert work.stage == Stage.TRANSCRIBED and not work.reports


def test_audio_only_invalid_and_retry(monkeypatch, recording):
    monkeypatch.setenv("GROQ_API_KEY", "offline")
    app = start()
    app.radio[0].set_value("Fichier audio").run()
    app.file_uploader(key="capture-file").upload("invalide.wav", b"invalide", "audio/wav").run()
    click(app, "Transcrire le vocal")
    assert app.error and app.session_state.runtime.spent == 0

    def transcribe(self, filename, data, mime):
        return Transcript(
            text="La visite est terminée.", language=None, duration=None, segments=None
        )

    monkeypatch.setattr(
        "src.providers.groq_transcription.GroqTranscriptionService.transcribe", transcribe
    )
    app.file_uploader(key="capture-file").upload(*recording).run()
    click(app, "Transcrire le vocal")
    assert button(app, GENERATE).disabled
    click(app, "Enregistrer la note")
    assert app.session_state.repo.data.works[0].note.text == "La visite est terminée."
