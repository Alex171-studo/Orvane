import hashlib
import json

from openai import OpenAI

from src.domain.errors import ExtractionError, ProviderAuthenticationError, SchemaValidationError
from src.domain.models import Proposal
from src.prompts.registry import PROMPTS


class OpenAIExtractionService:
    def __init__(self, settings, runtime, client=None):
        self.settings = settings
        self.runtime = runtime
        if client is None and not settings.OPENAI_API_KEY.get_secret_value():
            raise ProviderAuthenticationError("La clé OpenAI manque dans la configuration serveur.")
        self.client = client or OpenAI(
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            base_url="https://api.openai.com/v1",
            max_retries=0,
            timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        )

    def extract(self, source, context, reference):
        cfg = self.settings
        payload = json.dumps(
            {
                "chantier": context.name,
                "lieu": context.location,
                "date_reference": reference.isoformat(),
                "note": source,
            },
            ensure_ascii=False,
        )
        key = (
            "OpenAI",
            cfg.OPENAI_MODEL,
            cfg.PROMPT_VERSION,
            cfg.MAX_EXTRACTION_OUTPUT_TOKENS,
            hashlib.sha256(payload.encode()).digest(),
        )

        def request(metric):
            # Inspect completion before the native helper attempts to parse truncated JSON.
            raw = self.client.responses.with_raw_response.parse(
                model=cfg.OPENAI_MODEL,
                instructions=PROMPTS[cfg.PROMPT_VERSION],
                input=[{"role": "user", "content": payload}],
                text_format=Proposal,
                max_output_tokens=cfg.MAX_EXTRACTION_OUTPUT_TOKENS,
                store=False,
            )
            body = raw.http_response.json()
            if not isinstance(body, dict):
                raise SchemaValidationError("Réponse OpenAI invalide.")
            metric.request_id = raw.headers.get("x-request-id")
            metric.model = body.get("model") or cfg.OPENAI_MODEL
            usage = body.get("usage") or {}
            if not isinstance(usage, dict):
                raise SchemaValidationError("Métadonnées de consommation invalides.")
            metric.input_tokens = usage.get("input_tokens")
            metric.output_tokens = usage.get("output_tokens")
            if body.get("status") == "incomplete":
                reason = (body.get("incomplete_details") or {}).get("reason")
                raise ExtractionError(
                    "Limite de tokens atteinte. Raccourcissez la note."
                    if reason == "max_output_tokens"
                    else "Résultat incomplet. Votre transcription est conservée."
                )
            if body.get("status") != "completed":
                raise ExtractionError("Le traitement OpenAI n'a pas abouti.")
            output = body.get("output")
            if not isinstance(output, list) or any(
                not isinstance(i, dict)
                or (i.get("type") == "message" and not isinstance(i.get("content"), list))
                for i in output
            ):
                raise SchemaValidationError("Format de réponse OpenAI invalide.")
            response = raw.parse()
            if any(
                part.type == "refusal"
                for item in response.output
                if item.type == "message"
                for part in item.content
            ):
                raise ExtractionError("Le modèle a refusé cette extraction.")
            if not isinstance(response.output_parsed, Proposal):
                raise SchemaValidationError("Aucune extraction structurée valide.")
            return response.output_parsed

        return self.runtime.run(key, "OpenAI", cfg.OPENAI_MODEL, ExtractionError, request)
