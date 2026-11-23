import io
import json
import wave

import groq
import httpx
import openai
import pytest

from src.config.settings import Settings
from src.domain.errors import (
    BudgetError,
    ExtractionError,
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
    SchemaValidationError,
    TranscriptionError,
)
from src.providers.groq_transcription import GroqTranscriptionService
from src.providers.openai_extraction import OpenAIExtractionService
from src.providers.runtime import CallRuntime
from src.services.extraction_service import FieldIntelligencePipeline


def sdk(provider, handler):
    cls = openai.OpenAI if provider == "OpenAI" else groq.Groq
    return cls(
        api_key="offline-fixture",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def response_body(proposal):
    return {
        "id": "resp_offline",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5.4-mini-test",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "id": "msg_1",
                "status": "completed",
                "content": [
                    {"type": "output_text", "annotations": [], "text": proposal.model_dump_json()}
                ],
            }
        ],
        "usage": {"input_tokens": 123, "output_tokens": 45, "total_tokens": 168},
    }


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "NONE"))
        output.writeframes(bytes(640))
    return buffer.getvalue()


def test_native_structured_flow(session, caplog):
    _, wf, w, example, _ = session
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json=response_body(example.proposal), headers={"x-request-id": "req_test"}
        )

    cfg = Settings(MAX_API_CALLS_PER_SESSION=1)
    runtime = CallRuntime(cfg)
    pipe = FieldIntelligencePipeline(
        OpenAIExtractionService(cfg, runtime, sdk("OpenAI", handler)), cfg
    )
    wf.transcribe(w, example.text)
    wf.approve(w)
    with caplog.at_level("INFO"):
        wf.analyze(w, pipe)
        pipe.analyze(w.note.text, wf.repo.project(w.note.project_id), w.reference_datetime)
    wf.validate(w)
    assert len(calls) == 1 and calls[0]["text"]["format"]["strict"]
    assert calls[0]["store"] is False
    assert "UUID" not in json.dumps(calls[0]["text"]["format"])
    metric = runtime.metrics[0]
    assert metric.input_tokens == 123 and metric.request_id == "req_test"
    assert metric.model == "gpt-5.4-mini-test" and metric.duration_ms > 0
    assert example.text not in caplog.text and "offline-fixture" not in caplog.text
    with pytest.raises(BudgetError):
        pipe.analyze(
            "Autre note de terrain.", wf.repo.project(w.note.project_id), w.reference_datetime
        )


@pytest.mark.parametrize(
    "mode,error",
    [
        (400, ExtractionError),
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (422, ExtractionError),
        (429, ProviderRateLimitError),
        (500, ProviderServerError),
        ("network", ProviderNetworkError),
        ("timeout", ProviderTimeoutError),
        ("refusal", ExtractionError),
        ("incomplete", ExtractionError),
        ("filtered", ExtractionError),
        ("failed", ExtractionError),
        ("malformed", SchemaValidationError),
        ("empty", SchemaValidationError),
    ],
)
def test_openai_failures(mode, error, session):
    repo, wf, w, example, _ = session

    def handler(request):
        if isinstance(mode, int):
            return httpx.Response(mode, json={"error": {"message": "sensitive transcript!"}})
        if mode == "timeout":
            raise httpx.ReadTimeout("private")
        if mode == "network":
            raise httpx.ConnectError("private")
        body = response_body(example.proposal)
        if mode == "refusal":
            body["output"][0]["content"] = [{"type": "refusal", "refusal": "private"}]
        elif mode in ("incomplete", "filtered"):
            body.update(
                status="incomplete",
                incomplete_details={
                    "reason": "max_output_tokens" if mode == "incomplete" else "content_filter"
                },
            )
            body["output"][0]["content"][0]["text"] = "{"
        elif mode == "failed":
            body["status"] = "failed"
        elif mode == "malformed":
            body["output"][0]["content"][0]["text"] = "not JSON"
        else:
            body["output"] = []
        return httpx.Response(200, json=body)

    cfg = Settings()
    runtime = CallRuntime(cfg)
    service = OpenAIExtractionService(cfg, runtime, sdk("OpenAI", handler))
    with pytest.raises(error) as caught:
        service.extract(example.text, repo.project(w.note.project_id), w.reference_datetime)
    assert "private" not in str(caught.value) and runtime.spent == 1
    assert runtime.metrics[-1].error_type


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "Le mur est terminé."},
        {
            "text": "Le mur est terminé.",
            "duration": 3.2,
            "language": "fr",
            "segments": [{"start": 0.0, "end": 3.2, "text": "Le mur est terminé."}],
        },
        {"text": ""},
        {"text": "ok"},
        None,
    ],
)
def test_groq(payload):
    def handler(req):
        assert (
            b"note.wav" in req.content and b"verbose_json" in req.content and b"RIFF" in req.content
        )
        return (
            httpx.Response(200, json=payload)
            if payload is not None
            else httpx.Response(401, json={"error": "bad key"})
        )

    cfg = Settings()
    runtime = CallRuntime(cfg)
    service = GroqTranscriptionService(cfg, runtime, sdk("Groq", handler))
    if payload is None or len(payload["text"]) < 5:
        with pytest.raises((TranscriptionError, ProviderAuthenticationError)):
            service.transcribe("private.wav", wav())
    else:
        result = service.transcribe("private.wav", wav())
        assert result.duration == payload.get("duration") and result.text == payload["text"]
        assert service.transcribe("private.wav", wav()) == result
    assert runtime.spent == 1


def test_retry_only_rejected(monkeypatch):
    monkeypatch.setattr("src.providers.runtime.time.sleep", lambda seconds: None)
    replies = iter(
        [
            httpx.Response(429, json={"error": "quota"}),
            httpx.Response(200, json={"text": "La dalle est prête."}),
        ]
    )
    cfg = Settings(MAX_ATTEMPTS=2)
    runtime = CallRuntime(cfg)
    service = GroqTranscriptionService(cfg, runtime, sdk("Groq", lambda req: next(replies)))
    assert service.transcribe("note.wav", wav()).text == "La dalle est prête."
    assert runtime.spent == 2 and len(runtime.metrics) == 2


def test_note_instructions_stay_in_user_data(session):
    from src.prompts.registry import PROMPTS
    from src.services.evaluation_service import corpus

    case, expected = corpus()[17]
    cfg = Settings()
    repo, _, w, example, _ = session
    raw = example.proposal.model_copy(deep=True)
    raw.actions[0].description = "Appeler le fournisseur"
    raw.actions[0].source_excerpt = "Karim doit appeler le fournisseur."
    raw.actions[0].due_expression = None
    raw.issues = []
    raw.decisions = []
    raw.observations = []

    def handler(req):
        body = json.loads(req.content)
        assert body["instructions"] == PROMPTS["v2"]
        assert "Alice" not in body["instructions"] and "tools" not in body
        assert body["input"][0]["role"] == "user"
        assert json.loads(body["input"][0]["content"])["note"] == case["text"]
        return httpx.Response(200, json=response_body(raw))

    provider = OpenAIExtractionService(cfg, CallRuntime(cfg), sdk("OpenAI", handler))
    result = FieldIntelligencePipeline(provider, cfg).analyze(
        case["text"], repo.project(w.note.project_id), w.reference_datetime
    )
    assert [a.assignee for a in result.actions] == [expected["actions"][0]["assignee"]]


def test_exhausted_account_is_not_retried(session):
    repo, _, w, example, _ = session
    cfg = Settings(MAX_ATTEMPTS=3)
    runtime = CallRuntime(cfg)
    client = sdk(
        "OpenAI",
        lambda req: httpx.Response(
            429, json={"error": {"message": "quota", "code": "insufficient_quota"}}
        ),
    )
    provider = OpenAIExtractionService(cfg, runtime, client)
    with pytest.raises(ProviderRateLimitError):
        provider.extract(example.text, repo.project(w.note.project_id), w.reference_datetime)
    assert runtime.spent == 1
