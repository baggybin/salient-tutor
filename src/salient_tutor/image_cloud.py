"""Cloud image-generation backends for the tutor's illustrations.

Alternatives to the local ComfyUI/flux box (:mod:`salient_tutor.illustrations`):
MiniMax ``image-01`` and GLM/Zhipu CogView. Each reads its OWN
API key from the environment (the same pattern as :mod:`salient_tutor.minimax_tts`)
and returns raw PNG/JPEG bytes; :mod:`illustrations` still owns the fence
contract, the server-side brand style, hashing, and the content-addressed cache.

Design (per the Fable/council review):

  * **Opt-in per provider.** A backend whose key isn't set is simply absent from
    the model dial — no error, no config. ``configured()`` gates it.
  * **Style is portable, negatives are not.** The brand style words ride along in
    the positive prompt (plain text, any model honors it). These providers have
    no reliable negative-prompt field, so the *text ban* (the important half) is
    re-expressed as prose negation appended to the prompt; the quality bans are
    dropped (the positive style vocabulary covers them). Never fold the raw
    negative noun-list into the prompt — that would *request* text/watermarks.
  * **Write bytes now, never a provider URL.** MiniMax/GLM image URLs expire;
    we always fetch/decode to bytes immediately so the cached PNG is durable.
  * **No GPU semaphore.** Cloud calls are network I/O; each backend has its own
    small concurrency cap. Only the local backend guards the single GPU.
  * **Non-deterministic.** These don't reproduce pixels from a seed, so the
    cache is an *idempotency* key (first render wins; a re-emitted fence hits the
    cache and never re-bills). :mod:`illustrations` enforces that.
"""

from __future__ import annotations

import asyncio
import base64
import os

import httpx

_TIMEOUT = 120.0
# Appended to the positive prompt for providers without a negative field: the
# text ban is the half worth keeping (a mnemonic image must not spell things out).
_NEGATION = (
    " Absolutely no text, letters, numbers, words, captions, watermarks, "
    "or signatures anywhere in the image."
)


def _env(*names: str) -> str | None:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return None


def _raise_for(resp, provider: str) -> None:
    """Raise with the provider's response BODY on an HTTP error, not just the
    status — a 400 from these APIs carries the real reason (bad size, bad model,
    content refusal) in the body, which is what we need to see on the card."""
    if resp.status_code >= 400:
        raise RuntimeError(f"{provider} {resp.status_code}: {resp.text[:400]}")


class CloudBackend:
    """One cloud image model. Subclasses set ``name``/keys and implement
    :meth:`_generate`. ``deterministic`` is always False (cache = idempotency)."""

    name: str = ""
    deterministic: bool = False

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(2)  # courtesy rate-limit; NOT the GPU lock

    def configured(self) -> bool:
        raise NotImplementedError

    async def generate(self, prompt: str, width: int, height: int) -> bytes:
        """Return image bytes for ``prompt`` at ~``width``x``height`` (snapped to
        the provider's menu inside). Raises on any failure; the caller maps that
        to a graceful ``(None, error)``."""
        async with self._sem:
            return await self._generate(prompt + _NEGATION, width, height)

    async def _generate(self, prompt: str, width: int, height: int) -> bytes:
        raise NotImplementedError


def _aspect(width: int, height: int) -> str:
    """Nearest provider-friendly aspect ratio string for a requested w×h."""
    r = width / height if height else 1.0
    table = {"1:1": 1.0, "16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "3:4": 3 / 4}
    return min(table, key=lambda k: abs(table[k] - r))


class MinimaxImage(CloudBackend):
    """MiniMax ``image-01`` via ``/v1/image_generation`` (Bearer MINIMAX_API_KEY,
    region host MINIMAX_API_HOST). Reuses the credential the minimax_* agents and
    the read-aloud TTS already use."""

    name = "minimax-image"

    def configured(self) -> bool:
        return _env("MINIMAX_API_KEY") is not None

    async def _generate(self, prompt: str, width: int, height: int) -> bytes:
        key = _env("MINIMAX_API_KEY")
        host = _env("MINIMAX_API_HOST") or "https://api.minimax.io"
        body = {
            "model": "image-01",
            "prompt": prompt,
            "aspect_ratio": _aspect(width, height),
            "n": 1,
            "response_format": "base64",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{host.rstrip('/')}/v1/image_generation",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
            _raise_for(r, "minimax")
            data = r.json()
        # MiniMax nests the payload under "data"; base64 lives in image_base64,
        # else it returns expiring URLs we must fetch immediately.
        d = data.get("data") or {}
        b64 = d.get("image_base64") or data.get("image_base64")
        if b64:
            return base64.b64decode(b64[0] if isinstance(b64, list) else b64)
        urls = d.get("image_urls") or d.get("image_url")
        if urls:
            return await _fetch(urls[0] if isinstance(urls, list) else urls)
        raise RuntimeError(f"minimax: no image in response ({str(data)[:200]})")


class GlmImage(CloudBackend):
    """GLM image generation via the Z.ai / BigModel v4 images endpoint (Bearer
    GLM_API_KEY / ZHIPU_API_KEY). Defaults to the international z.ai gateway and
    the ``glm-image`` model; override ``GLM_API_HOST`` (e.g.
    ``https://open.bigmodel.cn/api/paas/v4`` for the China region) and
    ``GLM_IMAGE_MODEL`` (e.g. ``cogview-4``). Returns a URL we fetch immediately."""

    name = "glm-image"

    def configured(self) -> bool:
        return _env("GLM_API_KEY", "ZHIPU_API_KEY") is not None

    async def _generate(self, prompt: str, width: int, height: int) -> bytes:
        key = _env("GLM_API_KEY", "ZHIPU_API_KEY")
        host = _env("GLM_API_HOST") or "https://api.z.ai/api/paas/v4"
        model = _env("GLM_IMAGE_MODEL") or "glm-image"
        # Takes discrete size strings; snap to the closest square/wide/tall.
        size = _glm_size(width, height)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{host.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "prompt": prompt, "size": size},
            )
            _raise_for(r, "glm")
            data = r.json()
        items = data.get("data") or []
        if items and items[0].get("url"):
            return await _fetch(items[0]["url"])
        if items and items[0].get("b64_json"):
            return base64.b64decode(items[0]["b64_json"])
        raise RuntimeError(f"glm: no image in response ({str(data)[:200]})")


def _glm_size(width: int, height: int) -> str:
    # z.ai glm-image caps each dimension (error 1214: must be between 512px and a
    # max below 1440); keep the longer side at 1280, which the docs list as valid.
    r = width / height if height else 1.0
    if r > 1.2:
        return "1280x720"
    if r < 0.83:
        return "720x1280"
    return "1024x1024"


async def _fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(url)
        _raise_for(r, "fetch")
        return r.content


# Registry: name → backend instance. Import-time construction is cheap (no I/O);
# `configured()` is what gates a backend into the dial.
BACKENDS: dict[str, CloudBackend] = {b.name: b for b in (MinimaxImage(), GlmImage())}


def configured_models() -> list[str]:
    """Cloud model names whose API key is present — the union illustrations adds
    to the local registry for the model dial."""
    return [name for name, b in BACKENDS.items() if b.configured()]


def get(name: str) -> CloudBackend | None:
    return BACKENDS.get(name)
