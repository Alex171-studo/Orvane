import streamlit as st
from pydantic import ValidationError
from streamlit.errors import StreamlitSecretNotFoundError
from streamlit.logger import get_logger

from src.config.settings import Settings
from src.domain.errors import OrvaneError
from src.providers.runtime import CallRuntime
from src.services.workflow_service import Workflow
from src.storage.session_repository import SessionRepository
from src.ui.pages import capture, notebook, open_work
from src.ui.styles import brand

st.set_page_config(
    page_title="ORVANE · Compte rendu de chantier",
    page_icon=":material/architecture:",
    initial_sidebar_state="collapsed",
)
try:
    secrets = st.secrets.to_dict()
except StreamlitSecretNotFoundError:
    secrets = {}
try:
    cfg = Settings.load(secrets)
except ValidationError:
    st.error("Configuration serveur invalide. Vérifiez les paramètres de l’application.")
    st.stop()

get_logger("orvane.processing").setLevel("INFO")
if "repo" not in st.session_state:
    st.session_state.repo = SessionRepository()
repo = st.session_state.repo
if "runtime" not in st.session_state:
    st.session_state.runtime = CallRuntime(cfg, repo.data.metrics)
runtime = st.session_state.runtime
runtime.metrics = repo.data.metrics
wf = Workflow(repo, cfg)
brand()
try:
    notebook(repo, cfg, runtime)
    if error := st.session_state.pop("processing_error", None):
        st.error(error)
    if note_id := st.session_state.get("active_note"):
        open_work(repo, wf, cfg, runtime, repo.work(note_id))
    else:
        capture(repo, wf, cfg, runtime)
except OrvaneError as exc:
    st.error(str(exc))
except ValidationError:
    st.error("Vérifiez les valeurs saisies avant de continuer.")
