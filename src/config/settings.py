import os
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class Settings(BaseModel):
    APP_MODE: Literal["demo", "live"] = "demo"
    APP_TIMEZONE: str = "Europe/Paris"
    APP_ACCESS_TOKEN: SecretStr = SecretStr("")
    GROQ_API_KEY: SecretStr = SecretStr("")
    OPENAI_API_KEY: SecretStr = SecretStr("")
    GROQ_TRANSCRIPTION_MODEL: Literal["whisper-large-v3-turbo", "whisper-large-v3"] = (
        "whisper-large-v3-turbo"
    )
    TRANSCRIPTION_LANGUAGE: str = Field("fr", pattern=r"^[a-z]{2}$")
    OPENAI_MODEL: str = Field("gpt-5.4-mini", pattern=r"^gpt-5\.4(-mini)?(-\d{4}-\d{2}-\d{2})?$")
    OPENAI_EVAL_MODEL: str = Field("gpt-5.4", pattern=r"^gpt-5\.4(-mini)?(-\d{4}-\d{2}-\d{2})?$")
    MAX_AUDIO_SIZE_MB: int = Field(20, ge=1, le=25)
    MAX_TRANSCRIPT_CHARS: int = Field(30000, ge=20, le=100000)
    MAX_EXTRACTION_OUTPUT_TOKENS: int = Field(4096, ge=64, le=32768)
    MAX_API_CALLS_PER_SESSION: int = Field(10, ge=1, le=200)
    MAX_ATTEMPTS: int = Field(1, ge=1, le=3)
    OPENAI_REQUEST_TIMEOUT_SECONDS: float = Field(60, gt=0, le=300)
    GROQ_REQUEST_TIMEOUT_SECONDS: float = Field(60, gt=0, le=300)
    PROMPT_VERSION: Literal["v1", "v2"] = "v2"

    @field_validator("APP_TIMEZONE")
    @classmethod
    def timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Fuseau horaire inconnu.") from None
        return value

    @model_validator(mode="after")
    def check_live(self):
        if self.APP_MODE == "live" and len(self.APP_ACCESS_TOKEN.get_secret_value().strip()) < 24:
            raise ValueError("Le mode connecté exige une invitation d'au moins 24 caractères.")
        return self

    @classmethod
    def load(cls, secrets=None):
        merged = {**dotenv_values(".env"), **os.environ, **(secrets or {})}
        return cls.model_validate({k: merged[k] for k in cls.model_fields if k in merged})
