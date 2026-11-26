from datetime import datetime, time
from zoneinfo import ZoneInfo

import streamlit as st

from src.domain.errors import AudioValidationError, OrvaneError
from src.domain.models import Project, Stage, now
from src.providers.groq_transcription import GroqTranscriptionService
from src.providers.openai_extraction import OpenAIExtractionService
from src.services.audio_service import MIMES
from src.services.extraction_service import FieldIntelligencePipeline
from src.services.reporting_service import render_pdf
from src.services.validation_service import prepare
from src.storage.session_repository import SessionRepository
from src.ui.editors import read_report, review


def select_note(note_id=None):
    st.session_state.active_note = note_id


def notebook(repo, cfg, runtime):
    with st.sidebar:
        works = [w for w in reversed(repo.data.works) if w.note.source_type != "demo"]
        if works:
            st.subheader("Mes notes")
            for w in works:
                project = repo.project(w.note.project_id)
                st.button(
                    f"{project.name} · {w.reference_datetime:%d/%m}",
                    key=f"open-{w.note.id}",
                    on_click=select_note,
                    args=(w.note.id,),
                )
        with st.expander("Sauvegarde de session"):
            st.caption("Les notes restent dans cette session. Exportez-les pour les conserver.")
            st.download_button(
                "Exporter en JSON", repo.export_json(), "orvane.json", "application/json"
            )
            upload = st.file_uploader("Importer une archive", type=["json"], key="archive")
            restore = st.button("Remplacer la session par l’archive", disabled=upload is None)
            clear = st.checkbox("Effacer toutes mes notes")
            reset = st.button("Effacer la session", disabled=not clear)
            if restore or reset:
                replacement = SessionRepository()
                if restore:
                    replacement.restore(upload.getvalue(), cfg.MAX_TRANSCRIPT_CHARS)
                for key in list(st.session_state):
                    if key not in ("runtime", "repo"):
                        del st.session_state[key]
                st.session_state.repo = replacement
                runtime.completed.clear()
                runtime.metrics = replacement.data.metrics
                st.rerun()


def audio_source(cfg, runtime, source, prefix):
    if source == "Microphone":
        upload = st.audio_input("Enregistrer un message", key=f"{prefix}-mic")
    else:
        upload = st.file_uploader(
            "Choisir un fichier audio", type=list(MIMES), key=f"{prefix}-file"
        )
    configured = bool(cfg.GROQ_API_KEY.get_secret_value().strip())
    if not configured:
        st.caption("Transcription vocale indisponible. Vous pouvez saisir le texte.")
    if upload is None:
        return None, None
    if upload.size > cfg.MAX_AUDIO_SIZE_MB * 1_000_000:
        raise AudioValidationError(f"Le vocal dépasse {cfg.MAX_AUDIO_SIZE_MB} Mo.")
    # A replacement recording must never inherit the previous recording's transcript.
    key = f"{prefix}-{upload.file_id}"
    cached = st.session_state.get(f"meta-{prefix}")
    if cached and cached[0] == key:
        return cached
    if st.button("Transcrire le vocal", disabled=not configured, key=f"transcribe-{key}"):
        with st.spinner("Transcription en cours…"):
            transcript = GroqTranscriptionService(cfg, runtime).transcribe(
                upload.name, upload.getvalue(), upload.type
            )
        st.session_state[f"meta-{prefix}"] = (key, transcript)
        st.session_state[f"text-{key}"] = transcript.text
        return key, transcript
    return key, None


def analyze(wf, work, cfg, runtime):
    if work.stage == Stage.TRANSCRIBED:
        wf.approve(work)
    try:
        with st.spinner("Rédaction du compte rendu…"):
            provider = OpenAIExtractionService(cfg, runtime)
            wf.analyze(work, FieldIntelligencePipeline(provider, cfg))
    except OrvaneError as exc:
        st.session_state.processing_error = str(exc)
    st.rerun()


def analysis_button(cfg, text):
    enabled = bool(cfg.OPENAI_API_KEY.get_secret_value().strip())
    if not enabled:
        st.caption("Analyse IA indisponible. Vous pouvez enregistrer votre note.")
    return st.button(
        "Confirmer et générer le compte rendu",
        type="primary",
        disabled=not enabled or not text.strip(),
        help="Envoyer le texte relu à OpenAI.",
    )


def capture(repo, wf, cfg, runtime):
    st.title("Nouvelle note")
    left, right = st.columns([2, 1])
    name = left.text_input("Chantier", max_chars=160)
    tz = ZoneInfo(cfg.APP_TIMEZONE)
    visit = right.date_input("Date de visite", now().astimezone(tz).date(), format="DD/MM/YYYY")
    source = st.radio("Saisie", ["Texte", "Microphone", "Fichier audio"], horizontal=True)
    key = "written"
    transcript = None
    if source != "Texte":
        key, transcript = audio_source(cfg, runtime, source, "capture")
        if transcript is None and cfg.GROQ_API_KEY.get_secret_value().strip():
            return
    text = st.text_area(
        "Note de chantier" if source == "Texte" else "Transcription à relire",
        key=f"text-{key or 'manual'}",
        height=180,
        max_chars=cfg.MAX_TRANSCRIPT_CHARS,
    )
    generate = analysis_button(cfg, text)
    save = st.button("Enregistrer la note", disabled=not text.strip())
    if not (generate or save):
        return
    prepare(text, cfg.MAX_TRANSCRIPT_CHARS)
    project_name = name.strip() or "Chantier non renseigné"
    project = next(
        (
            p
            for p in repo.data.projects
            if p.name == project_name and p.reference_timezone == cfg.APP_TIMEZONE
        ),
        None,
    )
    if project is None:
        project = Project(
            name=project_name, location="Lieu non renseigné", reference_timezone=cfg.APP_TIMEZONE
        )
        repo.data.projects.append(project)
    work = wf.create(
        project, datetime.combine(visit, time(12), tz), "text" if source == "Texte" else "audio"
    )
    wf.transcribe(work, text, transcript)
    select_note(work.note.id)
    st.session_state.pop("meta-capture", None)
    if generate:
        analyze(wf, work, cfg, runtime)
    st.rerun()


def open_work(repo, wf, cfg, runtime, w):
    project = repo.project(w.note.project_id)
    st.title("Compte rendu de chantier" if w.reports else "Note de chantier")
    st.text(f"{project.name} · {w.reference_datetime:%d/%m/%Y}")
    with st.expander(
        "Note source", expanded=w.stage not in (Stage.IN_REVIEW, Stage.VALIDATED, Stage.EXPORTED)
    ):
        text = st.text_area(
            "Texte de la note",
            w.note.text,
            key=f"source-{w.note.id}",
            max_chars=cfg.MAX_TRANSCRIPT_CHARS,
        )
        if text != w.note.text:
            wf.revise_text(w, text)
    active_report = w.stage in (Stage.IN_REVIEW, Stage.VALIDATED, Stage.EXPORTED)
    if not active_report and analysis_button(cfg, text):
        analyze(wf, w, cfg, runtime)
    validated = [r for r in w.reports if r.status == "validated"]
    if validated:
        report = validated[-1]
        if len(validated) > 1:
            rev = st.selectbox("Version du PDF", [r.revision for r in reversed(validated)])
            report = next(r for r in validated if r.revision == rev)
        current = report is w.reports[-1] and w.stage in (Stage.VALIDATED, Stage.EXPORTED)
        st.download_button(
            f"Télécharger le PDF validé · V{report.revision}",
            render_pdf(report, project),
            f"orvane-{w.note.id.hex[:8]}-v{report.revision}.pdf",
            "application/pdf",
            on_click=wf.exported if current else "ignore",
            args=(w,) if current else (),
        )
    if active_report:
        if w.reports[-1].status == "draft" or st.toggle(
            "Modifier le rapport", key=f"edit-{w.reports[-1].id}"
        ):
            review(repo, wf, w)
        else:
            read_report(w.reports[-1].extraction)
    st.button("Nouvelle note", on_click=select_note, icon=":material/add:")
