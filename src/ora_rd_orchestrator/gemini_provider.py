"""Gemini Vertex AI provider for the LLM abstraction layer.

Extracted from ``ora_automation_api.chat_router`` — the auth, SSL, and HTTP
helpers here are the canonical implementations shared by both the orchestrator
pipeline and the chat API.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import time
from urllib import error, request

from .llm_provider import LLMProvider, ModelTier, TIER_DEFAULT_TIMEOUTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers (used by both GeminiProvider and chat_router)
# ---------------------------------------------------------------------------

def _resolve_ca_bundle() -> str:
    """Return a CA bundle path, preferring env vars then certifi."""
    env_bundle = os.getenv("ORA_RD_CA_BUNDLE", "").strip() or os.getenv("SSL_CERT_FILE", "").strip()
    if env_bundle and os.path.exists(env_bundle):
        return env_bundle
    try:
        import certifi
        bundle = certifi.where()
        if bundle and os.path.exists(bundle):
            return bundle
    except Exception:
        pass
    return ""


_cached_ssl_ctx: ssl.SSLContext | None = None
_ssl_ctx_checked: bool = False


def _get_ssl_context() -> ssl.SSLContext | None:
    """Return a cached SSL context with CA bundle, or None."""
    global _cached_ssl_ctx, _ssl_ctx_checked
    if _ssl_ctx_checked:
        return _cached_ssl_ctx
    ca_bundle = _resolve_ca_bundle()
    if ca_bundle:
        _cached_ssl_ctx = ssl.create_default_context(cafile=ca_bundle)
    _ssl_ctx_checked = True
    return _cached_ssl_ctx


def _urlopen(req: request.Request, timeout: float):
    """Open a URL request with retry and cached SSL context."""
    ctx = _get_ssl_context()
    retries = 2
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if ctx:
                return request.urlopen(req, timeout=timeout, context=ctx)
            return request.urlopen(req, timeout=timeout)
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(1.0 * attempt)
    raise last_exc or RuntimeError("HTTP request failed")


# Token cache: (token_str, expiry_monotonic)
_token_cache: tuple[str, float] | None = None
_TOKEN_CACHE_TTL = 50 * 60  # 50 minutes (tokens valid for ~60 min)


def _get_gemini_token() -> str:
    """Obtain a Google OAuth token with 50-minute caching."""
    global _token_cache
    now = time.monotonic()
    if _token_cache is not None:
        cached_token, expiry = _token_cache
        if now < expiry:
            return cached_token

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not cred_path or not os.path.exists(cred_path):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set or file missing")

    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(GoogleAuthRequest())
    if not credentials.token:
        raise RuntimeError("Failed to obtain Google OAuth token")

    _token_cache = (credentials.token, now + _TOKEN_CACHE_TTL)
    return credentials.token


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Gemini Vertex AI provider with multi-region failover."""

    _DEFAULT_MODELS: dict[str, str] = {
        ModelTier.LITE: "gemini-2.0-flash-lite",
        ModelTier.FLASH: "gemini-2.5-flash",
        ModelTier.PRO: "gemini-2.5-pro",
    }

    # Env var overrides per tier
    _MODEL_ENV_KEYS: dict[str, str] = {
        ModelTier.LITE: "ORA_RD_GEMINI_MODEL_LITE",
        ModelTier.FLASH: "ORA_RD_GEMINI_MODEL_FLASH",
        ModelTier.PRO: "ORA_RD_GEMINI_MODEL_PRO",
    }

    def is_available(self) -> bool:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
        return bool(cred_path and os.path.exists(cred_path) and project_id)

    def provider_name(self) -> str:
        return "Gemini Vertex AI"

    def __init__(self) -> None:
        self._model_cache: dict[str, str] = {}
        self._locations_cache: list[str] | None = None

    def _resolve_model(self, tier: str) -> str:
        cached = self._model_cache.get(tier)
        if cached is not None:
            return cached
        env_key = self._MODEL_ENV_KEYS.get(tier, "")
        if env_key:
            env_val = os.getenv(env_key, "").strip()
            if env_val:
                self._model_cache[tier] = env_val
                return env_val
        model = self._DEFAULT_MODELS.get(tier, self._DEFAULT_MODELS[ModelTier.FLASH])
        self._model_cache[tier] = model
        return model

    def _resolve_locations(self) -> list[str]:
        if self._locations_cache is not None:
            return self._locations_cache
        primary = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip() or "us-central1"
        fallback_raw = os.getenv("GOOGLE_CLOUD_FALLBACK_LOCATIONS", "").strip()
        fallback = [x.strip() for x in fallback_raw.split(",") if x.strip()]
        self._locations_cache = [primary] + [x for x in fallback if x != primary]
        return self._locations_cache

    def call(
        self,
        system_prompt: str,
        user_content: str,
        tier: str = ModelTier.FLASH,
        timeout: float | None = None,
        temperature: float | None = None,
    ) -> str:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
        if not project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID not set")

        model = self._resolve_model(tier)
        locations = self._resolve_locations()
        effective_timeout = timeout or TIER_DEFAULT_TIMEOUTS.get(tier, 60.0)
        effective_temperature = temperature if temperature is not None else 0.4

        token = _get_gemini_token()

        body: dict = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {
                "temperature": effective_temperature,
                "responseMimeType": "application/json",
            },
        }
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

        last_error: Exception | None = None
        for location in locations:
            url = (
                f"https://{location}-aiplatform.googleapis.com/v1/"
                f"projects/{project_id}/locations/{location}"
                f"/publishers/google/models/{model}:generateContent"
            )
            req = request.Request(
                url=url,
                data=body_bytes,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with _urlopen(req, timeout=effective_timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                payload = json.loads(raw)
                candidates = payload.get("candidates", [])
                if not isinstance(candidates, list) or not candidates:
                    raise RuntimeError("Gemini response missing candidates")
                parts = candidates[0].get("content", {}).get("parts", [])
                texts: list[str] = []
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and part.get("text"):
                            texts.append(str(part["text"]))
                result = "\n".join(texts).strip()
                logger.debug(
                    "Gemini %s (%s) @ %s: %d chars",
                    model, tier, location, len(result),
                )
                return result
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = RuntimeError(
                    f"Gemini HTTP {exc.code} at {location}: {detail[:600]}"
                )
                logger.warning("Gemini %s @ %s failed: HTTP %d", model, location, exc.code)
                continue
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini %s @ %s failed: %s", model, location, exc)
                continue

        raise last_error or RuntimeError("All Gemini locations failed")
