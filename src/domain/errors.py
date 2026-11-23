class OrvaneError(Exception):
    """Erreur présentable à l'utilisateur, sans contenu de requête."""


class AudioValidationError(OrvaneError):
    pass


class TranscriptionError(OrvaneError):
    pass


class ExtractionError(OrvaneError):
    pass


class ProviderAuthenticationError(OrvaneError):
    pass


class ProviderRateLimitError(OrvaneError):
    pass


class ProviderTimeoutError(OrvaneError):
    pass


class ProviderNetworkError(OrvaneError):
    pass


class ProviderServerError(OrvaneError):
    pass


class SchemaValidationError(ExtractionError):
    pass


class InvalidWorkflowTransition(OrvaneError):
    pass


class BudgetError(OrvaneError):
    pass
