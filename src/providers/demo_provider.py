import json
from pathlib import Path

from src.domain.errors import ExtractionError
from src.domain.models import Model, Proposal
from src.services.validation_service import normalize

DATA = Path(__file__).resolve().parents[2] / "data"


class Example(Model):
    name: str
    location: str
    text: str
    reference_datetime: str
    proposal: Proposal


def examples():
    return [
        Example.model_validate_json(json.dumps(item))
        for item in json.loads((DATA / "demo/sites.json").read_text())
    ]


class DemoProvider:
    def extract(self, source, context, reference):
        for example in examples():
            if example.name == context.name and normalize(example.text) == source:
                return example.proposal
        raise ExtractionError(
            "Cette note ne correspond à aucun exemple préenregistré. Rechargez la note du chantier ou utilisez le mode connecté."
        )
