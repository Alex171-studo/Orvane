from datetime import datetime
from zoneinfo import ZoneInfo

from src.domain.errors import SchemaValidationError
from src.domain.models import ExtractionResult, ProjectContext
from src.services.validation_service import materialize, prepare


class FieldIntelligencePipeline:
    def __init__(self, provider, settings):
        self.provider = provider
        self.settings = settings

    def analyze(
        self, transcript: str, project_context: ProjectContext, reference_datetime: datetime
    ) -> ExtractionResult:
        source = prepare(transcript, self.settings.MAX_TRANSCRIPT_CHARS)
        if reference_datetime.utcoffset() is None:
            raise SchemaValidationError("La date de référence doit comporter un fuseau horaire.")
        reference = reference_datetime.astimezone(ZoneInfo(project_context.reference_timezone))
        proposal = self.provider.extract(source, project_context, reference)
        return materialize(proposal, source, reference.date())
