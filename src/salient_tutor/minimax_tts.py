"""MiniMax text-to-audio (TTS) REST client for the tutor's read-aloud feature.

Ported from the salient operator console so salient-tutor's web modal can read
lessons aloud without a new dependency beyond ``httpx``. Speech synthesis hits
MiniMax's T2A v2 endpoint (``/v1/t2a_v2``) authed with a Bearer
``${MINIMAX_API_KEY}`` — the same credential the ``minimax_*`` agents already
use, so no new secret is introduced. The region host follows
``${MINIMAX_API_HOST}`` (defaults to the international gateway).

The non-streaming T2A v2 response carries the audio as a **hex-encoded** string
in ``data.audio``; we decode it to raw bytes (mp3 by default) for the caller to
hand to a browser ``<audio>`` element. All I/O is plain ``httpx`` (async).

If no ``MINIMAX_API_KEY`` is configured the web layer skips the TTS routes
gracefully — the read-aloud buttons simply never appear.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_TIMEOUT = 60.0
# International gateway; the China region is api.minimaxi.com — override with
# MINIMAX_API_HOST so the region follows the existing agent config.
DEFAULT_HOST = "https://api.minimax.io"
DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICE = "English_expressive_narrator"
DEFAULT_FORMAT = "mp3"
DEFAULT_SAMPLE_RATE = 32000
DEFAULT_BITRATE = 128000
DEFAULT_PITCH = 0
DEFAULT_VOL = 1.0
PITCH_RANGE = (-12, 12)
VOL_RANGE = (0.1, 2.0)
SPEED_RANGE = (0.5, 2.0)
SUPPORTED_FORMATS: tuple[str, ...] = ("mp3", "wav", "pcm", "flac")
SUPPORTED_SAMPLE_RATES: tuple[int, ...] = (8000, 16000, 22050, 24000, 32000, 44100)
SUPPORTED_BITRATES: tuple[int, ...] = (32000, 64000, 128000, 256000)
SUPPORTED_MODELS: tuple[str, ...] = (
    "speech-2.8-hd",  # current default — high-fidelity, slower
    "speech-2.8-turbo",  # current-gen fast tier
    "speech-2.6-hd",  # prior-gen HD (stable fallback)
)

# Decoded-audio ceiling — a single tutor reply is small (well under 1 MB).
MAX_AUDIO_BYTES = 16 * 1024 * 1024

_MIME_BY_FORMAT = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
    "flac": "audio/flac",
}


def api_key() -> str | None:
    """The configured MiniMax API key, or None when TTS is unavailable."""
    return (os.environ.get("MINIMAX_API_KEY", "") or "").strip() or None


def api_host() -> str:
    """The configured MiniMax API host (region gateway)."""
    return (os.environ.get("MINIMAX_API_HOST", "") or "").strip() or DEFAULT_HOST


def group_id() -> str | None:
    """Optional MiniMax GroupId (required only for the China region)."""
    return (os.environ.get("MINIMAX_GROUP_ID", "") or "").strip() or None


def available() -> bool:
    """Whether TTS can run (an API key is configured)."""
    return api_key() is not None


def mime_for(fmt: str) -> str:
    """Map an audio ``format`` to its MIME type (default mp3 → audio/mpeg)."""
    return _MIME_BY_FORMAT.get((fmt or "").lower(), "audio/mpeg")


# Curated subset of MiniMax's T2A v2 **system** voice_ids. The `id` strings are
# EXACT entries from the platform's System Voice ID List — the API rejects any
# unknown id with error 2054 ("voice id not exist"), so these must never be
# guessed or casing-normalized.
VOICE_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "English_expressive_narrator",
        "lang": "en",
        "gender": "neutral",
        "style": "narrator",
        "label": "Narrator (English, expressive)",
    },
    {
        "id": "English_CalmWoman",
        "lang": "en",
        "gender": "female",
        "style": "calm",
        "label": "Calm Woman (English)",
    },
    {
        "id": "English_Trustworth_Man",
        "lang": "en",
        "gender": "male",
        "style": "trustworthy",
        "label": "Trustworthy Man (English)",
    },
    {
        "id": "English_Graceful_Lady",
        "lang": "en",
        "gender": "female",
        "style": "graceful",
        "label": "Graceful Lady (English)",
    },
    {
        "id": "English_ManWithDeepVoice",
        "lang": "en",
        "gender": "male",
        "style": "deep",
        "label": "Man with Deep Voice (English)",
    },
    {
        "id": "English_FriendlyPerson",
        "lang": "en",
        "gender": "neutral",
        "style": "friendly",
        "label": "Friendly Person (English)",
    },
    {
        "id": "English_PatientMan",
        "lang": "en",
        "gender": "male",
        "style": "patient",
        "label": "Patient Man (English)",
    },
    {
        "id": "English_WiseScholar",
        "lang": "en",
        "gender": "male",
        "style": "scholarly",
        "label": "Wise Scholar (English)",
    },
    {
        "id": "English_radiant_girl",
        "lang": "en",
        "gender": "female",
        "style": "radiant",
        "label": "Radiant Girl (English)",
    },
    {
        "id": "English_Upbeat_Woman",
        "lang": "en",
        "gender": "female",
        "style": "upbeat",
        "label": "Upbeat Woman (English)",
    },
    {
        "id": "English_ConfidentWoman",
        "lang": "en",
        "gender": "female",
        "style": "confident",
        "label": "Confident Woman (English)",
    },
    {
        "id": "English_CaptivatingStoryteller",
        "lang": "en",
        "gender": "neutral",
        "style": "storyteller",
        "label": "Captivating Storyteller (English)",
    },
)


def supported_voices() -> list[dict[str, str]]:
    """The curated T2A v2 voice catalog. Returns a fresh list."""
    return [dict(v) for v in VOICE_CATALOG]


def tts_defaults() -> dict[str, Any]:
    """The current effective defaults for :func:`synthesize`."""
    return {
        "voice": DEFAULT_VOICE,
        "model": DEFAULT_MODEL,
        "format": DEFAULT_FORMAT,
        "speed": 1.0,
        "pitch": DEFAULT_PITCH,
        "vol": DEFAULT_VOL,
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "bitrate": DEFAULT_BITRATE,
    }


def _origin(base_url: str | None) -> str:
    """Normalize a configured endpoint to a scheme+host for ``/v1/t2a_v2``."""
    b = (base_url or "").strip().rstrip("/")
    if not b:
        return DEFAULT_HOST
    for suffix in ("/anthropic", "/v1/messages", "/v1"):
        if b.endswith(suffix):
            b = b[: -len(suffix)]
    return b or DEFAULT_HOST


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def parse_audio(data: dict[str, Any]) -> bytes:
    """Decode a T2A v2 JSON response into raw audio bytes."""
    base = data.get("base_resp") or {}
    code = base.get("status_code")
    if code not in (0, None):
        raise RuntimeError(f"MiniMax TTS error {code}: {base.get('status_msg') or 'unknown'}")
    audio_hex = (data.get("data") or {}).get("audio")
    if not audio_hex:
        raise RuntimeError("MiniMax TTS returned no audio")
    try:
        audio = bytes.fromhex(audio_hex)
    except ValueError as e:
        raise RuntimeError(f"MiniMax TTS returned undecodable audio: {e}") from e
    if len(audio) > MAX_AUDIO_BYTES:
        raise RuntimeError(f"synthesized audio too large ({len(audio)} bytes > {MAX_AUDIO_BYTES})")
    return audio


# ── on-disk audio cache (opt-in via TUTOR_TTS_CACHE=1) ───────────────────────
_DEFAULT_TTS_CACHE_MAX_MB = 256
_TRUTHY = ("1", "true", "yes", "on")


def cache_enabled() -> bool:
    return (os.environ.get("TUTOR_TTS_CACHE", "") or "").strip().lower() in _TRUTHY


def cache_dir() -> Path:
    override = (os.environ.get("TUTOR_TTS_CACHE_DIR", "") or "").strip()
    return Path(override) if override else (Path.home() / ".salient-tutor" / "tts")


def _cache_max_bytes() -> int:
    raw = (os.environ.get("TUTOR_TTS_CACHE_MAX_MB", "") or "").strip()
    try:
        mb = int(raw) if raw else _DEFAULT_TTS_CACHE_MAX_MB
    except ValueError:
        mb = _DEFAULT_TTS_CACHE_MAX_MB
    return max(0, mb) * 1024 * 1024


def cache_key(
    text: str,
    *,
    voice: str,
    model: str,
    fmt: str,
    speed: float,
    pitch: int,
    vol: float,
    sample_rate: int,
    bitrate: int,
) -> str:
    blob = (
        "\n".join(
            str(x)
            for x in (
                voice,
                model,
                fmt,
                speed,
                pitch,
                vol,
                sample_rate,
                bitrate,
            )
        )
        + "\n"
        + text
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_lookup(key: str, fmt: str) -> bytes | None:
    if not cache_enabled():
        return None
    path = cache_dir() / f"{key}.{fmt}"
    try:
        if not path.is_file():
            return None
        data = path.read_bytes()
        try:
            os.utime(path, None)
        except OSError:
            pass
        return data
    except OSError:
        return None


def cache_store(key: str, fmt: str, audio: bytes) -> None:
    if not cache_enabled():
        return
    d = cache_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        final = d / f"{key}.{fmt}"
        tmp = d / f".{key}.{fmt}.part"
        tmp.write_bytes(audio)
        tmp.replace(final)
    except OSError:
        return
    _cache_evict(d)


def _cache_evict(d: Path) -> None:
    cap = _cache_max_bytes()
    if cap <= 0:
        return
    try:
        entries = [(f, f.stat()) for f in d.iterdir() if f.is_file() and not f.name.startswith(".")]
    except OSError:
        return
    total = sum(st.st_size for _, st in entries)
    if total <= cap:
        return
    for f, st in sorted(entries, key=lambda e: e[1].st_mtime):
        try:
            f.unlink()
        except OSError:
            continue
        total -= st.st_size
        if total <= cap:
            break


async def synthesize(
    text: str,
    *,
    key: str | None = None,
    base_url: str | None = None,
    grp_id: str | None = None,
    voice: str = DEFAULT_VOICE,
    model: str = DEFAULT_MODEL,
    fmt: str = DEFAULT_FORMAT,
    speed: float = 1.0,
    pitch: int = DEFAULT_PITCH,
    vol: float = DEFAULT_VOL,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    bitrate: int = DEFAULT_BITRATE,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """POST *text* to MiniMax T2A v2 and return the decoded audio bytes.

    ``key`` / ``base_url`` / ``grp_id`` default to the environment
    (:func:`api_key`, :func:`api_host`, :func:`group_id`). Raises
    ``RuntimeError`` when no key is configured or on an API-level failure.
    """
    resolved_key = key or api_key()
    if not resolved_key:
        raise RuntimeError("MINIMAX_API_KEY not configured — TTS unavailable")
    origin = _origin(base_url or api_host())
    url = f"{origin}/v1/t2a_v2"
    gid = grp_id or group_id()
    params = {"GroupId": gid} if gid else None
    body: dict[str, Any] = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice,
            "speed": float(speed),
            "vol": float(vol),
            "pitch": int(pitch),
        },
        "audio_setting": {
            "sample_rate": int(sample_rate),
            "bitrate": int(bitrate),
            "format": fmt,
            "channel": 1,
        },
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        resp = await client.post(url, params=params, json=body, headers=_headers(resolved_key))
    resp.raise_for_status()
    return parse_audio(resp.json())
