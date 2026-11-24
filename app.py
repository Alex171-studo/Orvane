import streamlit as st
from pydantic import ValidationError
from streamlit.errors import StreamlitSecretNotFoundError
from streamlit.logger import get_logger

from src.config.settings import Settings
from src.domain.errors import OrvaneError
from src.domain.models import Project
from src.providers.demo_provider import examples
from src.providers.runtime import CallRuntime
from src.services.workflow_service import Workflow
from src.storage.session_repository import SessionRepository
from src.ui.access import authorized, invitation_form
from src.ui.pages import NAV, acquisition, action_plan, overview, quality, reports
from src.ui.styles import brand

st.set_page_config(
    page_title="ORVANE · Suivi de chantier", page_icon=":material/architecture:", layout="wide"
)
try:
    secrets = st.secrets.to_dict()
except StreamlitSecretNotFoundError:
    secrets = {}
try:
    cfg = Settings.load(secrets)
except ValidationError:
    st.error(
        "Configuration serveur invalide. Vérifiez les variables et l’invitation du mode connecté."
    )
    st.stop()

get_logger("orvane.processing").setLevel("INFO")
brand()
if cfg.APP_MODE == "live" and not authorized(cfg):
    invitation_form(cfg)
    st.stop()
if cfg.APP_MODE == "demo" and not authorized(cfg):
    st.sidebar.badge("Mode démonstration", color="blue")
if "repo" not in st.session_state:
    repo = SessionRepository()
    if cfg.APP_MODE == "demo":
        repo.data.projects = [
            Project(name=e.name, location=e.location, reference_timezone=cfg.APP_TIMEZONE)
            for e in examples()
        ]
    st.session_state.repo = repo
repo = st.session_state.repo
if "runtime" not in st.session_state:
    st.session_state.runtime = CallRuntime(cfg, repo.data.metrics)
runtime = st.session_state.runtime
wf = Workflow(repo, cfg)
if "next_note" in st.session_state:
    st.session_state.working_note = st.session_state.pop("next_note")
nav = st.sidebar.radio("Navigation", NAV, key="nav", label_visibility="collapsed")
st.sidebar.divider()


def refresh_session(reset):
    runtime.completed.clear()
    for key in list(st.session_state):
        if key not in ("authorized_invitation", "runtime", "repo"):
            del st.session_state[key]
    if reset:
        del st.session_state.repo
        runtime.metrics = []
    else:
        runtime.metrics = repo.data.metrics
    st.rerun()


try:
    with st.sidebar.expander("Données de session"):
        st.caption(
            "L’archive conserve le texte et les rapports. Les vocaux restent dans la session."
        )
        st.download_button(
            "Exporter la session", repo.export_json(), "orvane-session.json", "application/json"
        )
        upload = st.file_uploader("Archive de session", type=["json"], key="archive")
        if st.button("Remplacer par l’archive", disabled=upload is None):
            repo.restore(upload.getvalue(), cfg.MAX_TRANSCRIPT_CHARS)
            refresh_session(False)
        confirm = st.checkbox("Effacer cette session")
        if st.button("Réinitialiser", disabled=not confirm):
            refresh_session(True)
    runtime.metrics = repo.data.metrics
    if nav == NAV[0]:
        overview(repo)
    elif nav == NAV[1]:
        acquisition(repo, wf, cfg, runtime)
    elif nav == NAV[2]:
        action_plan(repo, wf)
    elif nav == NAV[3]:
        reports(repo, wf)
    else:
        quality(repo, runtime)
except OrvaneError as exc:
    st.error(str(exc))
except ValidationError:
    st.error("Certaines valeurs sont manquantes ou invalides. Vérifiez les champs saisis.")
