"""One place that talks to the Gemini API. The key travels in a header so it never appears in a URL or an error."""

from __future__ import annotations

import os
import time

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
RETRY_STATUS = {404, 408, 429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    pass


class _Result:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


def models() -> list[str]:
    primary = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.1-flash-lite"
    fallback = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-flash-latest")
    ordered = [primary] + [name.strip() for name in fallback.split(",") if name.strip()]
    return list(dict.fromkeys(ordered))


def gemini_post(json: dict, timeout: float = 30, deadline: float | None = None) -> _Result:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise GeminiError("The assistant is not configured.")
    last = "no model answered"
    for model in models():
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining < 2:
                last = "time limit reached"
                break
            timeout = min(timeout, remaining)
        try:
            response = httpx.post(
                f"{BASE}/{model}:generateContent",
                json=json,
                headers={"x-goog-api-key": key},
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            last = f"{model} {type(exc).__name__}"
            continue
        if response.status_code == 200:
            return _Result(response.json())
        last = f"{model} HTTP {response.status_code}"
        if response.status_code not in RETRY_STATUS:
            break
    raise GeminiError(f"Gemini did not answer ({last}).")
