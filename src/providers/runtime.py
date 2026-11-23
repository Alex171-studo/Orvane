import logging
import random
import time
from collections.abc import Callable
from threading import Lock

import groq
import openai
from pydantic import ValidationError

from src.domain.errors import (
    BudgetError,
    OrvaneError,
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    SchemaValidationError,
)
from src.domain.models import ProcessingMetrics

logger = logging.getLogger("orvane.processing")


def translate(exc, default):
    if isinstance(exc, OrvaneError):
        return exc
    if isinstance(
        exc,
        (
            ValidationError,
            ValueError,
            openai.APIResponseValidationError,
            groq.APIResponseValidationError,
        ),
    ):
        return SchemaValidationError("Le résultat du fournisseur n'a pas pu être validé.")
    if isinstance(exc, (openai.APITimeoutError, groq.APITimeoutError)):
        return ProviderTimeoutError("Délai dépassé. Vérifiez votre quota avant de réessayer.")
    if isinstance(exc, (openai.APIConnectionError, groq.APIConnectionError)):
        return ProviderNetworkError("Connexion interrompue. Votre note reste dans cette session.")
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return ProviderAuthenticationError(
            "Accès refusé par le fournisseur. Vérifiez la configuration serveur."
        )
    if status == 429:
        return ProviderRateLimitError("Quota ou limite de débit atteint. Réessayez ultérieurement.")
    if status and status >= 500:
        return ProviderServerError("Service temporairement indisponible. Votre note est conservée.")
    return default("Requête refusée par le fournisseur. Vérifiez les paramètres.")


class CallRuntime:
    """Un seul traitement en vol par session. Chaque tentative réserve une unité."""

    def __init__(self, settings, metrics=None):
        self.settings = settings
        self.metrics = metrics if metrics is not None else []
        self.spent = 0
        self.lock = Lock()
        self.completed = {}

    def run(self, key, provider, model, default, operation: Callable):
        if not self.lock.acquire(blocking=False):
            raise BudgetError("Un traitement est déjà en cours.")
        try:
            if key in self.completed:
                return self.completed[key].model_copy(deep=True)
            for attempt in range(self.settings.MAX_ATTEMPTS):
                if self.spent >= self.settings.MAX_API_CALLS_PER_SESSION:
                    raise BudgetError("Limite d'appels de cette session atteinte.")
                self.spent += 1
                metric = ProcessingMetrics(provider=provider, model=model)
                start = time.monotonic()
                try:
                    result = operation(metric)
                except (openai.APIError, groq.APIError, ValueError, OrvaneError) as exc:
                    error = translate(exc, default)
                    metric.error_type = type(error).__name__
                    metric.request_id = getattr(exc, "request_id", None) or metric.request_id
                    # Only a rejected request (429) is safe enough for an opted-in retry.
                    if (
                        not isinstance(error, ProviderRateLimitError)
                        or getattr(exc, "code", None)
                        in (
                            "insufficient_quota",
                            "billing_hard_limit_reached",
                            "billing_not_active",
                        )
                        or attempt + 1 == self.settings.MAX_ATTEMPTS
                    ):
                        raise error from None
                else:
                    self.completed[key] = result.model_copy(deep=True)
                    return result
                finally:
                    metric.duration_ms = (time.monotonic() - start) * 1000
                    self.metrics.append(metric)
                    logger.info(
                        "processing=%s provider=%s model=%s ms=%.1f status=%s category=%s",
                        metric.id,
                        provider,
                        metric.model,
                        metric.duration_ms,
                        "error" if metric.error_type else "ok",
                        metric.error_type,
                    )
                time.sleep(2**attempt + random.uniform(0, 0.5))
        finally:
            self.lock.release()
