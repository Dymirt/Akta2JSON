"""Extract JSON using the official Mistral SDK and its European inference region."""

import argparse
import math
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from mistralai.client import Mistral
from mistralai.client.errors import MistralError, NoResponseError
from mistralai.client.models import BaseModelCard, FTModelCard
from mistralai.client.utils.logger import NoOpLogger

from .prompts import extraction_instructions


EU_BASE_URL = "https://api.eu.mistral.ai/v1"
DEFAULT_MODEL = "ministral-8b-2512"
DEFAULT_RETRY_AFTER = 60
MAX_RETRY_AFTER = 45 * 60


class RateLimitError(RuntimeError):
    def __init__(self, retry_after: int):
        super().__init__("Mistral EU zwrócił HTTP 429.")
        self.retry_after = retry_after


def _retry_after(value: str | None) -> int:
    if not value:
        return DEFAULT_RETRY_AFTER
    value = value.strip()
    if value.isascii() and value.isdigit():
        digits = value.lstrip("0")
        if len(digits) > len(str(MAX_RETRY_AFTER)):
            return MAX_RETRY_AFTER
        return min(int(digits or "0"), MAX_RETRY_AFTER)
    try:
        until = parsedate_to_datetime(value)
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        seconds = math.ceil((until - datetime.now(UTC)).total_seconds())
        return max(0, min(seconds, MAX_RETRY_AFTER))
    except (ValueError, TypeError, OverflowError):
        return DEFAULT_RETRY_AFTER


class MistralClient:
    def __init__(self, api_key: str, model: str, base_url: str = EU_BASE_URL):
        if base_url.removesuffix("/") not in {EU_BASE_URL, "https://api.eu.mistral.ai:443/v1"}:
            raise ValueError(f"MISTRAL_BASE_URL musi wskazywać regionalny adres {EU_BASE_URL}.")
        if not api_key or not api_key.isascii() or not api_key.isprintable() or any(c.isspace() for c in api_key):
            raise ValueError("Ustaw poprawny MISTRAL_API_KEY.")
        if not model or not model.isprintable() or any(c.isspace() for c in model):
            raise ValueError("Podaj identyfikator modelu przez --model lub MISTRAL_MODEL.")
        self._api_key = api_key
        self.model = model
        self.on_token_usage: Callable[[int, int], None] | None = None

    def _record_token_usage(self, response: httpx.Response) -> None:
        if self.on_token_usage is None or not response.is_success:
            return
        cost_header = response.headers.get("x-ratelimit-tokens-query-cost", "").strip()
        limit_header = response.headers.get("x-ratelimit-limit-tokens-minute", "").strip()
        for value in (cost_header, limit_header):
            if not (value.isascii() and value.isdigit() and len(value) <= 18):
                return
        cost, limit = int(cost_header), int(limit_header)
        if cost > 0 and limit > 0:
            self.on_token_usage(cost, limit)

    @classmethod
    def from_environment(cls, model: str | None = None):
        return cls(
            os.environ.get("MISTRAL_API_KEY", "").strip(),
            model if model is not None else os.environ.get("MISTRAL_MODEL", DEFAULT_MODEL),
            os.environ.get("MISTRAL_BASE_URL", EU_BASE_URL),
        )

    @contextmanager
    def _client(self) -> Iterator[Mistral]:
        try:
            response_hooks = {"response": [self._record_token_usage]}
            with httpx.Client(follow_redirects=False, event_hooks=response_hooks) as transport, Mistral(
                api_key=self._api_key, server="eu", client=transport,
                timeout_ms=90_000, retry_config=None, debug_logger=NoOpLogger(),
            ) as client:
                yield client
        except MistralError as error:
            if error.status_code == 429:
                raise RateLimitError(_retry_after(error.headers.get("Retry-After"))) from None
            if 200 <= error.status_code < 300:
                raise RuntimeError("Mistral zwrócił niepoprawną odpowiedź API.") from None
            raise RuntimeError(f"Mistral EU zwrócił HTTP {error.status_code}.") from None
        except (httpx.RequestError, NoResponseError):
            raise RuntimeError("Nie udało się odebrać odpowiedzi z Mistral EU.") from None

    def list_models(self) -> list[str]:
        with self._client() as client:
            models = client.models.list().data
        if models is None:
            raise RuntimeError("Mistral zwrócił niepoprawną listę modeli.")
        return sorted({
            model.id for model in models
            if isinstance(model, (BaseModelCard, FTModelCard)) and model.capabilities.completion_chat
            and not (isinstance(model, FTModelCard) and model.archived)
        })

    def complete(self, template: str, document: str) -> str:
        with self._client() as client:
            response = client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": extraction_instructions(template)},
                    {"role": "user", "content": document},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                top_p=1,
            )
        if not response.choices or len(response.choices) != 1:
            raise RuntimeError("Mistral nie zwrócił jednej odpowiedzi modelu.")
        choice = response.choices[0]
        if choice.finish_reason != "stop" or choice.message is None:
            raise RuntimeError("Mistral nie zakończył generowania pełnej odpowiedzi.")
        content = choice.message.content
        if isinstance(content, list):
            text = []
            for part in content:
                if part.type == "thinking":
                    continue
                if part.type != "text":
                    raise RuntimeError("Mistral zwrócił niepoprawny blok odpowiedzi.")
                text.append(part.text)
            content = "".join(text)
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Odpowiedź Mistrala nie zawiera tekstu.")
        return content


def models_main(argv):
    parser = argparse.ArgumentParser(prog="odwolania models", description="Wypisz dostępne modele czatu z Mistral EU")
    parser.parse_args(argv)
    try:
        models = MistralClient.from_environment().list_models()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Nie można pobrać listy modeli: {error}", file=sys.stderr)
        return 1
    for model in models:
        print(model)
    return 0
