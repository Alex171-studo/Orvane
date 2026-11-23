import hashlib
from io import BytesIO

from groq import Groq

from src.domain.errors import ProviderAuthenticationError, TranscriptionError
from src.domain.models import Segment, Transcript
from src.services.audio_service import validate_audio


class GroqTranscriptionService:
    def __init__(self, settings, runtime, client=None):
        self.settings = settings
        self.runtime = runtime
        if client is None and not settings.GROQ_API_KEY.get_secret_value():
            raise ProviderAuthenticationError("La clé Groq manque dans la configuration serveur.")
        self.client = client or Groq(
            api_key=settings.GROQ_API_KEY.get_secret_value(),
            base_url="https://api.groq.com",
            max_retries=0,
            timeout=settings.GROQ_REQUEST_TIMEOUT_SECONDS,
        )

    def transcribe(self, filename, data, mime=None):
        cfg = self.settings
        ext = validate_audio(filename, mime, data, cfg.MAX_AUDIO_SIZE_MB)
        key = (
            "Groq",
            cfg.GROQ_TRANSCRIPTION_MODEL,
            cfg.TRANSCRIPTION_LANGUAGE,
            hashlib.sha256(data).digest(),
        )

        def request(metric):
            raw = self.client.audio.transcriptions.with_raw_response.create(
                file=(f"note.{ext}", BytesIO(data)),
                model=cfg.GROQ_TRANSCRIPTION_MODEL,
                language=cfg.TRANSCRIPTION_LANGUAGE,
                temperature=0,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
            parsed = raw.parse()
            if not hasattr(parsed, "model_dump"):
                raise TranscriptionError("Réponse de transcription illisible.")
            result = parsed.model_dump()
            metric.request_id = raw.headers.get("x-request-id")
            if result.get("text") is not None and not isinstance(result["text"], str):
                raise TranscriptionError("Le service a retourné une transcription invalide.")
            text = (result.get("text") or "").strip()
            if not text:
                raise TranscriptionError(
                    "La transcription est vide. Vérifiez votre enregistrement audio."
                )
            if len(text) < 5:
                raise TranscriptionError(
                    "Transcription trop courte. Réécoutez ou saisissez la note."
                )
            if len(text) > cfg.MAX_TRANSCRIPT_CHARS:
                raise TranscriptionError(
                    "Transcription trop longue. Découpez votre enregistrement."
                )
            segments = result.get("segments")
            if segments is not None:
                if not isinstance(segments, list) or any(not isinstance(s, dict) for s in segments):
                    raise TranscriptionError("Métadonnées de segmentation invalides.")
                segments = [
                    Segment(**{k: s.get(k) for k in Segment.model_fields}) for s in segments
                ]
            return Transcript(
                text=text,
                language=result.get("language"),
                duration=result.get("duration"),
                segments=segments,
            )

        return self.runtime.run(
            key, "Groq", cfg.GROQ_TRANSCRIPTION_MODEL, TranscriptionError, request
        )
