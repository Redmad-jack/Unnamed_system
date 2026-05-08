from __future__ import annotations

import os

import httpx


_DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
_DEFAULT_TTS_VOICE = "alloy"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAITextToSpeech:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key or _voice_api_key()
        self._base_url = _voice_base_url(base_url)

    def create_speech(self, text: str) -> bytes:
        if not self._api_key:
            raise ValueError(
                "Missing HAVE_SOME_AI_VOICE_API_KEY or OPENAI_API_KEY "
                "for text-to-speech"
            )

        model = os.getenv("HAVE_SOME_AI_TTS_MODEL", _DEFAULT_TTS_MODEL)
        voice = os.getenv("HAVE_SOME_AI_TTS_VOICE", _DEFAULT_TTS_VOICE)
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            response = client.post(
                f"{self._base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "voice": voice,
                    "input": text,
                    "instructions": (
                        "Read like a calm exhibition robot. Speak clearly in Chinese "
                        "and English. Leave a short pause between sentences."
                    ),
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            return response.content


def _voice_api_key() -> str | None:
    return os.getenv("HAVE_SOME_AI_VOICE_API_KEY") or os.getenv("OPENAI_API_KEY")


def _voice_base_url(base_url: str | None = None) -> str:
    value = (
        base_url
        or os.getenv("HAVE_SOME_AI_VOICE_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or _DEFAULT_BASE_URL
    )
    return value.rstrip("/")
