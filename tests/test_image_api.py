"""Diffusion illustrations — salient_tutor.illustrations + POST /api/image.

Exercises the render() contract (disabled by default, spec parsing, closed
schema, deterministic seed/cache, model validation, graceful failure) with a
FAKE imagegen backend so nothing touches the GPU box, plus the endpoint + config
wiring. Mirrors test_diagram_api.py: no pytest-asyncio — coroutines run via
asyncio.run; TestClient without lifespan (the route doesn't touch the daemon).
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from salient_tutor import illustrations, web


# ── a fake imagegen backend (no ComfyUI, no network) ─────────────────────────
class _FakeResult:
    def __init__(self, data: bytes):
        self.png_bytes = data


class _FakeImageGen:
    calls = 0
    last_kwargs: dict = {}

    def __init__(self, *a, **k):
        pass

    def generate(self, prompt, **kw):
        type(self).calls += 1
        type(self).last_kwargs = {"prompt": prompt, **kw}
        # Echo the seed into the bytes so we can assert determinism if needed.
        return [_FakeResult(b"PNG:" + str(kw.get("seed")).encode())]


class _FakeMod:
    MODELS = {"flux-schnell": {}, "flux-dev": {}, "qwen": {}}
    ImageGenError = RuntimeError
    ImageGen = _FakeImageGen


def _use_fake(monkeypatch, tmp_path, *, enabled=True):
    if enabled:
        monkeypatch.setenv("TUTOR_IMAGES", "1")
    else:
        monkeypatch.delenv("TUTOR_IMAGES", raising=False)
    monkeypatch.setattr(illustrations, "_imagegen", lambda: _FakeMod)
    monkeypatch.setattr(illustrations, "_CACHE_DIR", tmp_path)
    _FakeImageGen.calls = 0


# ── enablement gate ──────────────────────────────────────────────────────────
def test_disabled_by_default(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path, enabled=False)
    assert illustrations.available() is False
    res, err = asyncio.run(illustrations.render("a scene", model="flux-schnell"))
    assert res is None
    assert "disabled" in err.lower()


def test_available_when_enabled_with_package(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    assert illustrations.available() is True
    assert illustrations.models() == ["flux-schnell", "flux-dev", "qwen"]


# ── spec parsing (closed schema) ─────────────────────────────────────────────
def test_parse_spec_prose_fallback():
    spec, err = illustrations.parse_spec("A giant glowing mitochondrion powering a city")
    assert err is None
    assert spec.scene.startswith("A giant glowing mitochondrion")
    assert spec.caption  # first line becomes caption


def test_parse_spec_keyed_fields_and_aspect():
    spec, err = illustrations.parse_spec(
        "caption: The cell's power plant\nscene: a glowing mitochondrion at dusk\naspect: tall"
    )
    assert err is None
    assert spec.caption == "The cell's power plant"
    assert spec.scene == "a glowing mitochondrion at dusk"
    assert (spec.width, spec.height) == illustrations._ASPECTS["tall"]


def test_parse_spec_unknown_keys_are_dropped():
    # `evil:` isn't in the closed schema → treated as prose, not honored.
    spec, err = illustrations.parse_spec("scene: a lake\nevil: rm -rf /")
    assert err is None
    assert spec.scene == "a lake"


def test_parse_spec_empty_and_oversize():
    _, e1 = illustrations.parse_spec("   ")
    assert "empty" in e1.lower()
    _, e2 = illustrations.parse_spec("x" * (illustrations._MAX_SRC + 1))
    assert "too large" in e2.lower()


# ── style is server-owned ────────────────────────────────────────────────────
def test_final_prompt_wraps_scene_with_brand_style():
    p = illustrations._final_prompt("a red canoe")
    assert "a red canoe" in p
    assert illustrations._STYLE_PREFIX in p
    assert illustrations._STYLE_SUFFIX in p
    assert illustrations._NEGATIVE.startswith("text,")  # split-enforcing negative


def test_seed_is_deterministic_from_spec():
    d = illustrations._digest("anything")
    assert illustrations._seed_from(d) == illustrations._seed_from(d)


# ── render happy path + cache ────────────────────────────────────────────────
def test_render_generates_then_cache_hits(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    src = "scene: a colossal glowing mitochondrion powering a sleeping city"

    r1, e1 = asyncio.run(illustrations.render(src, model="flux-schnell"))
    assert e1 is None
    assert r1.cached is False and r1.url.endswith(".png")
    assert _FakeImageGen.calls == 1
    # the PNG landed on disk under the (patched) cache dir
    digest = r1.url.split("/")[-1][:-4]
    assert illustrations.cache_file(digest) is not None

    r2, e2 = asyncio.run(illustrations.render(src, model="flux-schnell"))
    assert e2 is None
    assert r2.cached is True
    assert r2.url == r1.url
    assert _FakeImageGen.calls == 1  # no second generation


def test_render_unknown_model_rejected(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    res, err = asyncio.run(illustrations.render("a scene", model="dalle"))
    assert res is None
    assert "unknown or unavailable" in err.lower()


def test_render_backend_failure_is_graceful(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)

    def _boom(self, prompt, **kw):
        raise _FakeMod.ImageGenError("ComfyUI unreachable")

    monkeypatch.setattr(_FakeImageGen, "generate", _boom)
    res, err = asyncio.run(illustrations.render("scene: a lake", model="qwen"))
    assert res is None
    assert "failed" in err.lower()


# ── modes: mnemonic / loci / labeled ─────────────────────────────────────────
def test_mode_from_arg_and_body_line_override():
    spec, _ = illustrations.parse_spec("scene: a thing", mode="loci")
    assert spec.mode == "loci"
    # a body `mode:` line wins over the arg
    spec, _ = illustrations.parse_spec("mode: labeled\nscene: a thing", mode="mnemonic")
    assert spec.mode == "labeled"
    # unknown mode falls back to default
    spec, _ = illustrations.parse_spec("scene: a thing", mode="bogus")
    assert spec.mode == "mnemonic"


def test_profile_negatives_differ_by_mode():
    _, mnem_neg = illustrations._profile("mnemonic")
    _, lab_neg = illustrations._profile("labeled")
    assert mnem_neg.startswith("text,")  # bans text (split enforcement)
    assert "labels" not in lab_neg  # labeled ALLOWS short labels
    assert "paragraphs" in lab_neg  # but still bans prose blocks


def test_labeled_label_cap_rejected():
    dense = 'scene: a chart with "a" "b" "c" "d" "e" "f" callouts'
    spec, err = illustrations.parse_spec(dense, mode="labeled")
    assert spec is None
    assert "diagram engine" in err.lower()


def test_labeled_is_pinned_to_qwen(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    # Ask for flux-dev, but labeled mode must route to qwen server-side.
    r, e = asyncio.run(
        illustrations.render("scene: a JWT capsule train", model="flux-dev", mode="labeled")
    )
    assert e is None
    assert r.model == "qwen"
    # ...and it used the label-permitting negative profile.
    assert "labels" not in _FakeImageGen.last_kwargs["negative"]


def test_mode_is_part_of_cache_key(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    r1, _ = asyncio.run(illustrations.render("scene: a lake", model="flux-dev", mode="mnemonic"))
    r2, _ = asyncio.run(illustrations.render("scene: a lake", model="flux-dev", mode="loci"))
    assert r1.url != r2.url  # different mode → different digest → not a false cache hit


# ── council fence stripping (one image per tutor turn, never a fan-out) ───────
def test_strip_image_fences_removes_only_image_blocks():
    text = "before\n```image\nscene: a lake\n```\nmid\n```mermaid\nA-->B\n```\nafter"
    out = web._strip_image_fences({"a": text})["a"]
    assert "```image" not in out
    assert "```mermaid" in out  # diagrams survive
    assert "before" in out and "after" in out


# ── endpoint + config ────────────────────────────────────────────────────────
def test_endpoint_disabled_returns_error(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path, enabled=False)
    resp = TestClient(web.app).post("/api/image", json={"source": "a lake"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] is None
    assert body["error"]


def test_endpoint_generates_and_serves_png(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    client = TestClient(web.app)
    resp = client.post(
        "/api/image", json={"source": "scene: a lake at dawn", "model": "flux-schnell"}
    )
    assert resp.status_code == 200
    url = resp.json()["url"]
    assert url
    png = client.get(url)
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"PNG:")


def test_image_file_rejects_bad_digest(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    resp = TestClient(web.app).get("/api/image/not-a-hash.png")
    assert resp.status_code == 404


def test_config_exposes_images(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "daemon", None)
    body = TestClient(web.app).get("/api/config").json()
    assert "images" in body
    assert body["images"]["available"] is True
    assert body["images"]["models"] == ["flux-schnell", "flux-dev", "qwen"]


# ── workspaces ("schoolbags") ────────────────────────────────────────────────
def _no_pointer(monkeypatch, tmp_path):
    """Point the autoload pointer at a nonexistent file so tests don't read the
    real repo-root pointer a running server may have written."""
    monkeypatch.setattr(web, "_LAST_WS_FILE", tmp_path / "nope" / "ptr")


def test_work_root_default_is_absolute_repo_work(monkeypatch, tmp_path):
    monkeypatch.delenv("TUTOR_WORK_ROOT", raising=False)
    _no_pointer(monkeypatch, tmp_path)
    wr = web._resolve_work_root()
    assert wr.is_absolute()
    assert wr.name == "work"


def test_work_root_env_relative_resolves_under_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("TUTOR_WORK_ROOT", "work/schoolbag-bob")
    _no_pointer(monkeypatch, tmp_path)
    wr = web._resolve_work_root()
    assert wr.is_absolute()
    assert wr.name == "schoolbag-bob"
    assert wr.parent.name == "work"


def test_work_root_env_absolute_is_honored(monkeypatch, tmp_path):
    monkeypatch.setenv("TUTOR_WORK_ROOT", str(tmp_path / "alice"))
    _no_pointer(monkeypatch, tmp_path)
    assert web._resolve_work_root() == (tmp_path / "alice").resolve()


# ── autoload the last-used workspace ─────────────────────────────────────────
def test_autoload_uses_remembered_workspace(monkeypatch, tmp_path):
    monkeypatch.delenv("TUTOR_WORK_ROOT", raising=False)
    monkeypatch.setattr(web, "_LAST_WS_FILE", tmp_path / "ptr")
    # a previous run remembered work/bob
    web._remember_workspace((tmp_path / "work" / "bob").resolve())
    assert web._resolve_work_root() == (tmp_path / "work" / "bob").resolve()


def test_explicit_env_overrides_remembered(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "_LAST_WS_FILE", tmp_path / "ptr")
    web._remember_workspace((tmp_path / "bob").resolve())
    monkeypatch.setenv("TUTOR_WORK_ROOT", str(tmp_path / "alice"))
    assert web._resolve_work_root() == (tmp_path / "alice").resolve()


def test_remember_roundtrip_and_missing_pointer(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "_LAST_WS_FILE", tmp_path / "ptr")
    assert web._read_last_workspace() is None  # nothing written yet
    web._remember_workspace((tmp_path / "carol").resolve())
    assert web._read_last_workspace() == (tmp_path / "carol").resolve()


def test_configure_cache_points_images_at_workspace(tmp_path):
    illustrations.configure_cache(tmp_path / "wsA" / "images")
    assert illustrations._CACHE_DIR == (tmp_path / "wsA" / "images").resolve()
    # switching workspaces repoints the cache
    illustrations.configure_cache(tmp_path / "wsB" / "images")
    assert illustrations._CACHE_DIR == (tmp_path / "wsB" / "images").resolve()


def test_default_model_prefers_flux_dev(monkeypatch, tmp_path):
    _use_fake(monkeypatch, tmp_path)
    # flux-dev is preferred even when a "faster" model sorts ahead of it.
    assert illustrations.default_model(["flux-schnell", "flux-dev", "qwen"]) == "flux-dev"
    # falls back to the first installed when flux-dev is absent
    assert illustrations.default_model(["qwen"]) == "qwen"
    assert illustrations.default_model([]) is None


def test_config_exposes_workspace(monkeypatch):
    monkeypatch.setenv("TUTOR_WORK_ROOT", "work/schoolbag-bob")
    monkeypatch.setattr(web, "daemon", None)
    body = TestClient(web.app).get("/api/config").json()
    assert body["workspace"] == "schoolbag-bob"
