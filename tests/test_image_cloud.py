"""Cloud image backends (MiniMax / GLM) + their wiring into
illustrations.render — all HTTP mocked, no network, no keys required.

The load-bearing test is the billing guard: a re-emitted fence must hit the
content-addressed cache and make ZERO further HTTP calls (cloud renders cost
money and aren't seed-reproducible, so the cache is an idempotency key).
"""

from __future__ import annotations

import asyncio
import base64

from salient_tutor import illustrations, image_cloud

_PNG = b"\x89PNG\r\n\x1a\nCLOUDBYTES"


class _Resp:
    def __init__(self, *, json_data=None, content=b"", status=200, text=""):
        self._json = json_data
        self.content = content
        self.status_code = status
        self.text = text or (f"HTTP {status} body" if status >= 400 else "")

    def json(self):
        return self._json


class _FakeClient:
    """Records calls across instances so a test can assert HTTP was (not) made."""

    posts: list = []
    gets: list = []
    post_resp: _Resp | None = None
    get_resp: _Resp | None = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        type(self).posts.append((url, kw))
        return type(self).post_resp

    async def get(self, url, **kw):
        type(self).gets.append(url)
        return type(self).get_resp


def _use_cloud(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("TUTOR_IMAGES", "1")
    monkeypatch.setattr(illustrations, "_imagegen", lambda: None)  # no local box
    monkeypatch.setattr(illustrations, "_CACHE_DIR", tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for k in (
        "MINIMAX_API_KEY",
        "GLM_API_KEY",
        "ZHIPU_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        if k not in env:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(image_cloud, "httpx", _mk_httpx())
    _FakeClient.posts = []
    _FakeClient.gets = []


def _mk_httpx():
    class _H:
        AsyncClient = _FakeClient

    return _H


# ── configuration gating ──────────────────────────────────────────────────────
def test_cloud_absent_without_keys(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path)  # no keys
    assert image_cloud.configured_models() == []
    assert illustrations.available() is False  # no local box, no cloud key
    assert illustrations.models() == []


def test_minimax_appears_when_key_set(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="sk-test")
    assert "minimax-image" in image_cloud.configured_models()
    assert illustrations.available() is True
    assert "minimax-image" in illustrations.models()


# ── render via MiniMax + the billing guard ────────────────────────────────────
def test_minimax_render_then_cache_hit_zero_http(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="sk-test")
    _FakeClient.post_resp = _Resp(
        json_data={"data": {"image_base64": [base64.b64encode(_PNG).decode()]}}
    )

    res, err = asyncio.run(illustrations.render("scene: a whale", model="minimax-image"))
    assert err is None and res is not None
    assert res.model == "minimax-image" and res.cached is False
    assert len(_FakeClient.posts) == 1  # one generation call
    # the PNG landed on disk, content-addressed
    digest = res.url.split("/")[-1][:-4]
    assert illustrations.cache_file(digest) is not None
    assert illustrations.cache_file(digest).read_bytes() == _PNG

    # Re-emit the SAME fence → cache hit, NO further HTTP (the billing guard).
    res2, err2 = asyncio.run(illustrations.render("scene: a whale", model="minimax-image"))
    assert err2 is None and res2.cached is True
    assert len(_FakeClient.posts) == 1  # still one — did not re-bill


def test_minimax_http_error_surfaces_body(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="sk-test")
    _FakeClient.post_resp = _Resp(status=400, text='{"base_resp":{"status_msg":"invalid params"}}')
    res, err = asyncio.run(illustrations.render("scene: a whale", model="minimax-image"))
    assert res is None and err is not None
    assert "failed" in err.lower()
    assert "invalid params" in err  # the provider's real reason, not just "400"


def test_glm_fetches_url_to_bytes(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, GLM_API_KEY="sk-glm")
    _FakeClient.post_resp = _Resp(json_data={"data": [{"url": "https://cogview.example/x.png"}]})
    _FakeClient.get_resp = _Resp(content=_PNG)
    res, err = asyncio.run(illustrations.render("scene: a lantern", model="glm-image"))
    assert err is None and res is not None
    assert len(_FakeClient.posts) == 1 and len(_FakeClient.gets) == 1  # generate + fetch
    digest = res.url.split("/")[-1][:-4]
    assert illustrations.cache_file(digest).read_bytes() == _PNG


def test_unknown_cloud_model_rejected(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="sk-test")
    res, err = asyncio.run(illustrations.render("scene: x", model="dalle-99"))
    assert res is None and "unknown or unavailable" in err


# ── content-keyed artifact index: replay survives a style edit (no re-bill) ────
def test_content_index_survives_style_change(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="sk-test")
    _FakeClient.post_resp = _Resp(
        json_data={"data": {"image_base64": [base64.b64encode(_PNG).decode()]}}
    )
    res1, _ = asyncio.run(illustrations.render("a whale", model="minimax-image"))
    assert len(_FakeClient.posts) == 1

    # An edit to the server-owned style would change the styled digest (a genuine
    # cache miss under the old scheme). The content index must still resolve the
    # same fence to its original image — no regeneration, no re-bill.
    monkeypatch.setattr(illustrations, "_STYLE_SUFFIX", "completely different style words")
    res2, err2 = asyncio.run(illustrations.render("a whale", model="minimax-image"))
    assert err2 is None and res2.cached is True
    assert res2.url == res1.url
    assert len(_FakeClient.posts) == 1  # the style change did NOT re-bill


def test_regenerate_variant_forces_fresh(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="sk-test")
    _FakeClient.post_resp = _Resp(
        json_data={"data": {"image_base64": [base64.b64encode(_PNG).decode()]}}
    )
    asyncio.run(illustrations.render("a whale", model="minimax-image"))
    assert len(_FakeClient.posts) == 1
    # A regenerate carries a `# variant` nonce → forces past the index.
    res, err = asyncio.run(illustrations.render("a whale\n# variant abc123", model="minimax-image"))
    assert err is None and res.cached is False
    assert len(_FakeClient.posts) == 2


# ── startup provider summary ──────────────────────────────────────────────────
def test_provider_summary_lists_cloud(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path, MINIMAX_API_KEY="k", GLM_API_KEY="g")
    s = illustrations.provider_summary()
    assert s.startswith("on") and "minimax-image" in s and "glm-image" in s


def test_provider_summary_no_backend(monkeypatch, tmp_path):
    _use_cloud(monkeypatch, tmp_path)  # enabled, no local box, no cloud key
    assert "NO backend" in illustrations.provider_summary()


def test_provider_summary_disabled(monkeypatch):
    monkeypatch.delenv("TUTOR_IMAGES", raising=False)
    assert "off" in illustrations.provider_summary()
