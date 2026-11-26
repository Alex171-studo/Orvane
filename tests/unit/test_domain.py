import pytest
from pydantic import ValidationError

from src.config.settings import Settings
from src.domain.models import ProjectContext, ProposedAction


def test_settings():
    assert Settings().MAX_API_CALLS_PER_SESSION == 10
    for params in ({"APP_TIMEZONE": "../x"}, {"MAX_ATTEMPTS": 4}):
        with pytest.raises(ValidationError):
            Settings(**params)


def test_strict_schema():
    with pytest.raises(ValidationError):
        ProposedAction.model_validate_json('{"status":"Majeure"}')
    with pytest.raises(ValidationError):
        ProjectContext(name="", location="Lyon", reference_timezone="Europe/Paris")
