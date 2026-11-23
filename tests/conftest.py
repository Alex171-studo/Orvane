from datetime import datetime

import pytest

from src.config.settings import Settings
from src.domain.models import Project
from src.providers.demo_provider import DemoProvider, examples
from src.services.extraction_service import FieldIntelligencePipeline
from src.services.workflow_service import Workflow
from src.storage.session_repository import SessionRepository


@pytest.fixture
def session():
    cfg = Settings()
    example = examples()[0]
    repo = SessionRepository()
    project = Project(
        name=example.name, location=example.location, reference_timezone=cfg.APP_TIMEZONE
    )
    repo.data.projects.append(project)
    wf = Workflow(repo, cfg)
    work = wf.create(project, datetime.fromisoformat(example.reference_datetime), "demo")
    return repo, wf, work, example, FieldIntelligencePipeline(DemoProvider(), cfg)


@pytest.fixture
def reviewed(session):
    repo, wf, w, example, pipeline = session
    wf.transcribe(w, example.text)
    wf.approve(w)
    wf.analyze(w, pipeline)
    return repo, wf, w
