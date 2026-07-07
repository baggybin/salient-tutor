"""Server-side diffusion illustrations — drives ComfyUI via the ``imagegen`` pkg.

The tutor can emit a fenced ``image`` block whose body is a short *scene
description*; this module turns that into a branded PNG by calling the sibling
``imagegen`` package (which talks to ComfyUI on the ai.home GPU box). It is the
diffusion counterpart to :mod:`salient_tutor.diagrams`:

  * deterministic diagram engines keep exclusive ownership of anything a learner
    must *read* (flows, graphs, labels) — see prompts/tutor.md;
  * this module only ever renders *mnemonic / illustrative* imagery
    (method-of-loci scenes, visual metaphors, dual-coding art).

Design (validated against the council + Fable):

  * **Opt-in.** Off unless ``TUTOR_IMAGES=1``; if ``imagegen`` isn't installed or
    the GPU box is unreachable, :func:`available` is False and :func:`render`
    returns an error tuple — the app boots and teaches fine without it.
  * **Style is server-owned policy**, never authored by the model. A fixed prompt
    scaffold + fixed negative prompt (with ``text`` in it, which doubles as
    enforcement of the diagram/diffusion split) wrap the model's scene text.
  * **Deterministic seed** derived from the request hash → identical spec yields
    identical pixels → the content-addressed cache actually hits.
  * **Serialized** through a module ``asyncio.Semaphore(1)`` (one GPU) with the
    blocking client run in a worker thread; the cache is re-checked *after*
    acquiring the semaphore so a duplicated fence generates once.
  * **Bounded** by a hard deadline (a hung ComfyUI must not wedge the semaphore
    forever) and written atomically so the GET endpoint never serves a partial.
  * Never raises for expected failures — returns ``(result, None)`` or
    ``(None, error)`` exactly like :func:`salient_tutor.diagrams.render`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from salient_tutor import image_cloud

_log = logging.getLogger(__name__)

# ── Brand style policy (server-owned) ────────────────────────────────────────
# Encoded in *diffusion vocabulary*, not hex — Flux/SDXL don't honor hex codes.
# These describe the app's dark indigo/violet identity (mirrors app.css :root:
# --bg #0d1117, --bg-3 #1c2330, --accent #818cf8, --accent-2 #a78bfa).
_STYLE_PREFIX = (
    "flat modern educational illustration, clean vector-poster style, deep charcoal navy background"
)
_STYLE_SUFFIX = (
    "glowing indigo and soft violet accent lighting, muted desaturated palette, "
    "soft volumetric light, cohesive dark theme, subtle rim light, "
    "high concept, memorable and evocative"
)
# Mnemonic negative: the leading `text, letters, numbers, labels` both improves
# quality AND enforces the diagram/diffusion split — a mnemonic image should
# evoke, not spell things out.
_NEGATIVE = (
    "text, letters, numbers, words, labels, captions, watermark, signature, "
    "logo, bright white background, oversaturated, photorealistic, photograph, "
    "cluttered, busy background, ugly, deformed, low quality, jpeg artifacts"
)
# Loci (method-of-loci) negative: the isolation effect (von Restorff) needs ONE
# impossible/bizarre object to survive the sampler, so we DROP the "ugly,
# deformed" anatomy-flattening tokens that fight surreal physics — while keeping
# the text/quality bans. "extra fingers, mutated hands" is retained to kill true
# render *defects* (not surreal *content*). The single-bizarre-element discipline
# is enforced by the authoring prompt, not the negative (a negative can't count
# objects). Because the negative is part of the content-address (see _canonical),
# this re-keys loci images cleanly — old cached PNGs keep their old hash.
_NEGATIVE_LOCI = (
    "text, letters, numbers, words, labels, captions, watermark, signature, "
    "logo, bright white background, oversaturated, photorealistic, photograph, "
    "cluttered, busy background, extra fingers, mutated hands, low quality, jpeg artifacts"
)
# Labeled (informational) negative: text is DELIBERATELY allowed (short name
# callouts) — but still block paragraphs, gibberish typography, and chrome. Used
# only for the qwen-routed `labeled` mode, whose whole point is a few legible
# names on a depicted thing (council's "showing info" middle path).
_NEGATIVE_LABELED = (
    "paragraphs, sentences, dense text, gibberish text, misspelled text, "
    "watermark, signature, logo, bright white background, oversaturated, "
    "photorealistic, photograph, cluttered, busy background, ugly, deformed, "
    "low quality, jpeg artifacts"
)
_STYLE_SUFFIX_LABELED = (
    "glowing indigo and soft violet accents, muted dark palette, clean uncluttered "
    "layout, clear legible short labels, cohesive dark theme, infographic clarity"
)

# ── Modes ────────────────────────────────────────────────────────────────────
# The agent picks a mode; the SERVER owns model + negative-profile routing (the
# agent never names a model). `labeled` is the only text-bearing mode and is
# pinned to qwen ("best in-image text"); it also enforces a label-count cap so a
# mangled label in reference material can't become misinformation.
_MODES = ("mnemonic", "loci", "labeled")
_DEFAULT_MODE = "mnemonic"
_LABELED_MODEL = "qwen"  # only qwen renders legible in-image text
_MAX_LABELS = 5  # backstop for the text-precision gate (council rule 2)

# Models the selector may pick, in preference order. Kept in sync with
# imagegen.MODELS; validated at call time so an unknown/uninstalled model
# degrades to an error rather than a 500. flux-schnell (4-step, fastest) is
# preferred when installed; flux-dev is the reliable default (quality).
_MODELS = ("flux-schnell", "flux-dev", "qwen")
_DEFAULT_MODEL = "flux-dev"  # installed + verified on the box; safe default

_MAX_SRC = 2_000  # a scene description, not a document
_DEADLINE = 240.0  # hard cap (s); a hung box must not wedge the GPU semaphore
# Cache location: ABSOLUTE and anchored to the repo root, NOT the launch cwd — so
# images generated in a past session are never "lost" just because the server was
# later started from a different directory. Combined with deterministic seeding
# (identical spec → identical hash), a wiped cache also self-heals: reopening an
# old thread re-renders its ```image fences and regenerates the same files. Set
# TUTOR_IMAGE_CACHE to override. Nothing in this module ever deletes cached PNGs.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = (
    Path(os.environ["TUTOR_IMAGE_CACHE"]).resolve()
    if os.environ.get("TUTOR_IMAGE_CACHE")
    else _REPO_ROOT / "work" / "images"
)

# One GPU on the box → serialize generations. Waiters block on the async
# semaphore (no worker thread held), so the executor pool can't be exhausted.
_gpu = asyncio.Semaphore(1)


def configure_cache(path: str | Path) -> None:
    """Point the image cache at ``path`` (absolute), so images live alongside the
    rest of a workspace's data. Called at server startup with
    ``<work_root>/images``; a ``TUTOR_IMAGE_CACHE`` env override takes precedence
    and skips this. No-op-safe to call before any render."""
    global _CACHE_DIR
    _CACHE_DIR = Path(path).expanduser().resolve()


@dataclass
class ImageResult:
    url: str  # served by GET /api/image/{hash}.png
    cached: bool
    model: str
    seed: int


def _enabled() -> bool:
    return (os.environ.get("TUTOR_IMAGES") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _imagegen():
    """Import the optional dependency lazily. Returns the module or None."""
    try:
        import imagegen  # noqa: PLC0415
    except Exception:  # pragma: no cover - absence is the interesting branch
        return None
    return imagegen


def available() -> bool:
    """Feature is offerable: enabled AND at least one backend exists — the local
    imagegen package OR a configured cloud provider (MiniMax/GLM key set).

    Does not probe the GPU box (that would add latency to /api/config); a box
    that's down surfaces as a render-time error the client shows on the card."""
    return _enabled() and (_imagegen() is not None or bool(image_cloud.configured_models()))


def _local_models() -> list[str]:
    ig = _imagegen()
    have = set(getattr(ig, "MODELS", {})) if ig is not None else set()
    return [m for m in _MODELS if m in have]


def models() -> list[str]:
    """Selectable models (cheap, no network): the local imagegen registry unioned
    with cloud providers whose API key is configured.

    Local entries are the *plausible* set — a model here may still be
    un-downloaded on the box, in which case a render surfaces a graceful error.
    Used on the hot WS path (choice validation) where a network probe would block
    the event loop; :func:`installed_models` is the accurate variant for config."""
    return _local_models() + image_cloud.configured_models()


def provider_summary() -> str:
    """One-line, network-free summary of which image backends are live — for the
    server startup log, so a misconfigured key (provider absent) is obvious at
    boot rather than only when a render silently degrades to caption-only."""
    if not _enabled():
        return "off (set TUTOR_IMAGES=1 to enable)"
    local = _local_models()
    cloud = image_cloud.configured_models()
    if not local and not cloud:
        return "on, but NO backend (imagegen box absent and no cloud key set)"
    parts = []
    if local:
        parts.append("local: " + ", ".join(local))
    if cloud:
        parts.append("cloud: " + ", ".join(cloud))
    return "on — " + " | ".join(parts)


def installed_models() -> list[str]:
    """Models whose weights are actually present on the box (BLOCKING probe).

    Fails safe: on any error (box down, timeout) returns the cheap registry list
    so the client still offers a plausible selector rather than an empty one.
    Call off the event loop (e.g. ``asyncio.to_thread``)."""
    cloud = image_cloud.configured_models()
    ig = _imagegen()
    if ig is None:
        return cloud  # cloud-only install (no local box) still offers those models
    try:
        present = {m["name"] for m in ig.ImageGen().list_models() if m.get("installed")}
    except Exception:
        return models()  # box unreachable → plausible set (already includes cloud)
    ordered = [m for m in _MODELS if m in present]
    return (ordered or _local_models()) + cloud


def default_model(installed: list[str] | None = None) -> str | None:
    """The model to preselect. Prefer the verified default (flux-dev) whenever
    it's installed — some boxes report other weights as present but they fail at
    generation (e.g. an incomplete flux-schnell), and a broken default is worse
    than a slightly slower reliable one. Falls back to the first installed model.
    Pass an already-fetched ``installed`` list to avoid a second box probe."""
    inst = installed if installed is not None else installed_models()
    if _DEFAULT_MODEL in inst:
        return _DEFAULT_MODEL
    return inst[0] if inst else None


# ── spec parsing ─────────────────────────────────────────────────────────────
# The fence body is a *closed schema*: a first-line caption plus optional
# `key: value` directives we recognize; everything else is scene prose. Unknown
# keys are ignored (same instinct as diagrams' 20KB cap + SVG sanitize).
_KEY_RE = re.compile(r"^(caption|scene|aspect|mode)\s*:\s*(.+)$", re.IGNORECASE)
_ASPECTS = {
    "square": (1024, 1024),
    "wide": (1216, 832),
    "tall": (832, 1216),
}
_LABEL_RE = re.compile(r'"[^"]{1,40}"')  # quoted short callouts in labeled mode


@dataclass
class ImageSpec:
    scene: str
    caption: str
    width: int
    height: int
    mode: str


def parse_spec(source: str, mode: str = _DEFAULT_MODE) -> tuple[ImageSpec | None, str | None]:
    """Parse a fenced image body into an :class:`ImageSpec`.

    Accepts free prose (first non-empty line becomes the caption and the whole
    body the scene) and/or ``key: value`` lines (``caption``/``scene``/
    ``aspect``/``mode``). ``mode`` may come from the fence info string (passed
    in) or a body line (which wins). Returns ``(spec, None)`` or
    ``(None, error)``."""
    source = (source or "").strip()
    if not source:
        return None, "empty image spec"
    if len(source) > _MAX_SRC:
        return None, f"image spec too large ({len(source)} > {_MAX_SRC} chars)"

    caption = scene = ""
    aspect = "wide"
    prose: list[str] = []
    for ln in source.split("\n"):
        m = _KEY_RE.match(ln.strip())
        if not m:
            if ln.strip():
                prose.append(ln.strip())
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "caption":
            caption = val
        elif key == "scene":
            scene = val
        elif key == "aspect":
            aspect = val.lower()
        elif key == "mode":
            mode = val.lower()

    if not scene:
        scene = " ".join(prose) if prose else caption
    if not caption:
        caption = prose[0] if prose else scene
    if not scene.strip():
        return None, "image spec has no scene description"

    mode = mode if mode in _MODES else _DEFAULT_MODE
    # Text-precision backstop (council gate 2): a labeled image with too many
    # callouts belongs in a deterministic diagram, not diffusion.
    if mode == "labeled" and len(_LABEL_RE.findall(scene)) > _MAX_LABELS:
        return None, (
            f"labeled image has more than {_MAX_LABELS} labels — use a diagram "
            "engine (dot/mermaid) for dense labeled visuals"
        )

    w, h = _ASPECTS.get(aspect, _ASPECTS["wide"])
    return ImageSpec(
        scene=scene.strip(), caption=caption.strip()[:200], width=w, height=h, mode=mode
    ), None


# ── prompt / seed / cache ────────────────────────────────────────────────────
def _profile(mode: str) -> tuple[str, str]:
    """(style_suffix, negative) for a mode. `labeled` allows short in-image text;
    `loci` drops the anatomy-flattening bans so ONE impossible object can render
    (von Restorff isolation); everything else bans text + defects to keep the
    diagram/diffusion split clean."""
    if mode == "labeled":
        return _STYLE_SUFFIX_LABELED, _NEGATIVE_LABELED
    if mode == "loci":
        return _STYLE_SUFFIX, _NEGATIVE_LOCI
    return _STYLE_SUFFIX, _NEGATIVE


def _final_prompt(scene: str, mode: str = _DEFAULT_MODE) -> str:
    suffix, _ = _profile(mode)
    return f"{_STYLE_PREFIX}, {scene}, {suffix}"


def _canonical(model: str, prompt: str, negative: str, spec: ImageSpec) -> str:
    return "\x1f".join(
        [
            "v2",
            model,
            spec.mode,
            prompt,
            negative,
            str(spec.width),
            str(spec.height),
        ]
    )


def _digest(canonical: str) -> str:
    return hashlib.sha256(canonical.encode()).hexdigest()


def _seed_from(digest: str) -> int:
    # Deterministic, in ComfyUI's 0..2**31-1 range → same spec, same image.
    return int(digest[:8], 16)


def _cache_path(digest: str) -> Path:
    return _CACHE_DIR / f"{digest}.png"


def cache_file(digest: str) -> Path | None:
    """Path to a cached PNG for the GET endpoint, or None if absent/invalid."""
    if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
        return None
    p = _cache_path(digest)
    return p if p.exists() else None


# ── content-addressed artifact index ─────────────────────────────────────────
# The digest above keys the FILE on the fully-styled prompt (model + brand style
# + negative + size) — so editing any of those (we changed the loci negative
# once) re-keys history and a replayed fence misses → regenerates (a real re-bill
# for cloud models). This index keys DURABLE PERSISTENCE on the fence *content*
# instead (scene text + mode), mapping it to whatever URL was first produced. A
# replayed fence resolves to its original image regardless of later style/model
# edits — no churn, no re-bill. (Fence content, not styled prompt: "same scene"
# must survive a restyle; the file still keys on the full digest so two stylings
# never collide.)
_VARIANT_RE = re.compile(r"#\s*variant\s+\S+", re.IGNORECASE)


def _content_key(scene: str, mode: str) -> str:
    # Strip the regenerate nonce and normalize whitespace so trivial diffs (and a
    # regenerate) map to the same durable key.
    base = " ".join(_VARIANT_RE.sub("", scene).split())
    return hashlib.sha256(f"{mode}\x1f{base}".encode()).hexdigest()


def _index_path() -> Path:
    return _CACHE_DIR / "index.json"


def _index_load() -> dict[str, dict]:
    try:
        return json.loads(_index_path().read_text())
    except Exception:
        return {}


def _index_get(content_key: str) -> str | None:
    """The URL previously produced for this fence content, iff its file still
    exists on disk (a stale index entry whose PNG was deleted returns None)."""
    ent = _index_load().get(content_key) or {}
    url = ent.get("url")
    if url and cache_file(url.rsplit("/", 1)[-1][:-4]) is not None:
        return url
    return None


def _index_put(content_key: str, url: str) -> None:
    idx = _index_load()
    if idx.get(content_key, {}).get("url") == url:
        return
    idx[content_key] = {"url": url}
    try:
        _write_atomic(_index_path(), json.dumps(idx).encode())
    except Exception:  # best-effort; a lost write just re-hits the digest cache
        pass


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # atomic — GET never sees a partial file


def _generate_blocking(
    ig, model: str, prompt: str, negative: str, seed: int, spec: ImageSpec, digest: str
) -> None:
    """Runs in a worker thread: generate + cache. Writes even if the awaiting
    request was cancelled, so the work isn't wasted (retry hits cache)."""
    gen = ig.ImageGen(timeout=_DEADLINE)
    results = gen.generate(
        prompt,
        model=model,
        negative=negative,
        seed=seed,
        width=spec.width,
        height=spec.height,
        filename_prefix=f"tutor_{spec.mode}",
    )
    if not results:
        raise ig.ImageGenError("no image produced")
    _write_atomic(_cache_path(digest), results[0].png_bytes)


async def render(
    source: str, model: str | None = None, mode: str = _DEFAULT_MODE
) -> tuple[ImageResult | None, str | None]:
    """Render a fenced image ``source`` to a branded PNG.

    ``mode`` (mnemonic/loci/labeled) picks the style + negative profile and, for
    ``labeled``, pins the model to qwen (the only one that renders legible text);
    a body ``mode:`` line overrides the argument. Mirrors
    :func:`salient_tutor.diagrams.render`: returns ``(result, None)`` or
    ``(None, error)``; never raises for expected failures. On success the PNG is
    cached under ``work/images/<hash>.png`` and reachable at ``result.url``."""
    if not _enabled():
        return None, "image generation is disabled on this server"

    req_model = (model or _DEFAULT_MODEL).strip().lower()

    spec, err = parse_spec(source, mode=(mode or _DEFAULT_MODE).strip().lower())
    if err:
        return None, err
    assert spec is not None

    # Server owns model routing: labeled (text-bearing) is pinned to qwen; other
    # modes honor the caller's dial choice.
    eff_model = _LABELED_MODEL if spec.mode == "labeled" else req_model
    if eff_model not in models():
        return None, f"unknown or unavailable image model: {eff_model!r}"

    # Durable, content-keyed reuse: a replayed (or restyled) fence resolves to the
    # image it FIRST produced, regardless of later style/model/negative edits — no
    # regeneration, no cloud re-bill. A regenerate (```# variant```) forces past it.
    ckey = _content_key(spec.scene, spec.mode)
    force = "variant" in source.lower()
    if not force:
        prior = _index_get(ckey)
        if prior is not None:
            d0 = prior.rsplit("/", 1)[-1][:-4]
            _log.info("image HIT (index) %s model=%s", d0[:12], eff_model)
            return ImageResult(url=prior, cached=True, model=eff_model, seed=_seed_from(d0)), None

    _, negative = _profile(spec.mode)
    prompt = _final_prompt(spec.scene, spec.mode)
    # The FILE keys on the fully-styled prompt (model + brand style + negative +
    # size) so two stylings never collide; the derived seed is only *sent* to
    # backends that honor it (local flux). The content index (above) is what makes
    # replay survive a style edit.
    digest = _digest(_canonical(eff_model, prompt, negative, spec))
    seed = _seed_from(digest)
    url = f"/api/image/{digest}.png"

    # Fast path: already generated (self-healing for local, idempotency for cloud).
    if _cache_path(digest).exists():
        _log.info("image HIT (digest) %s model=%s", digest[:12], eff_model)
        _index_put(ckey, url)
        return ImageResult(url=url, cached=True, model=eff_model, seed=seed), None

    _log.info("image MISS %s model=%s — generating", digest[:12], eff_model)

    # ── Cloud backend: network I/O, its own concurrency cap, NEVER the GPU lock ──
    cloud = image_cloud.get(eff_model)
    if cloud is not None:
        try:
            png = await asyncio.wait_for(
                cloud.generate(prompt, spec.width, spec.height), timeout=_DEADLINE + 15
            )
        except TimeoutError:
            return None, f"image generation timed out after {_DEADLINE:.0f}s"
        except Exception as e:  # HTTP/4xx/content-refusal → graceful caption-only
            return None, f"image generation failed: {str(e)[:300]}"
        if not png:
            return None, "image generation produced no data"
        _write_atomic(_cache_path(digest), png)
        _index_put(ckey, url)
        return ImageResult(url=url, cached=False, model=eff_model, seed=seed), None

    # ── Local GPU backend ──
    ig = _imagegen()
    if ig is None:
        return None, "imagegen package is not installed on this server"
    try:
        async with _gpu:  # one GPU → serialize
            # Re-check under the lock: a duplicate fence that queued behind us
            # is now already on disk.
            if _cache_path(digest).exists():
                _index_put(ckey, url)
                return ImageResult(url=url, cached=True, model=eff_model, seed=seed), None
            await asyncio.wait_for(
                asyncio.to_thread(
                    _generate_blocking, ig, eff_model, prompt, negative, seed, spec, digest
                ),
                timeout=_DEADLINE + 15,
            )
    except TimeoutError:
        return None, f"image generation timed out after {_DEADLINE:.0f}s"
    except Exception as e:  # ImageGenError, network, bad model — surface tersely
        return None, f"image generation failed: {str(e)[:300]}"

    if not _cache_path(digest).exists():
        return None, "image generation produced no file"
    _index_put(ckey, url)
    return ImageResult(url=url, cached=False, model=eff_model, seed=seed), None
