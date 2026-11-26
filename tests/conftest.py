import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.config.settings import Settings
from src.domain.models import Project, Proposal
from src.services.extraction_service import FieldIntelligencePipeline
from src.services.workflow_service import Workflow
from src.storage.session_repository import SessionRepository


@pytest.fixture
def session():
    cfg = Settings()
    sample = json.loads((Path(__file__).parent / "fixtures/proposal.json").read_text())
    sample["proposal"] = Proposal.model_validate_json(json.dumps(sample["proposal"]))
    example = SimpleNamespace(**sample)
    repo = SessionRepository()
    project = Project(
        name=example.name, location=example.location, reference_timezone=cfg.APP_TIMEZONE
    )
    repo.data.projects.append(project)
    wf = Workflow(repo, cfg)
    work = wf.create(project, datetime.fromisoformat(example.reference_datetime), "text")
    return (
        repo,
        wf,
        work,
        example,
        FieldIntelligencePipeline(Mock(extract=Mock(return_value=example.proposal)), cfg),
    )


@pytest.fixture
def reviewed(session):
    repo, wf, w, example, pipeline = session
    wf.transcribe(w, example.text)
    wf.approve(w)
    wf.analyze(w, pipeline)
    return repo, wf, w
