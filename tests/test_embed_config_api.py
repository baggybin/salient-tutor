"""Embeddings config + backfill — the operator-facing gear modal plumbing.

Covers the three pieces salient-tutor wires on top of salient-core's embedder:
  1. embed_config() / set_embed_config() — resolved view + persist/clear to
     work/embed_config.json, with the api_key never echoed back.
  2. The GET/POST /api/embed/config routes.
  3. The backfill loop actually embeds pending KG facts when an embedder is
     configured (using a stubbed Embedder so no HTTP is made).
  4. /api/embed/models fail-safe: an unreachable server returns reachable:false,
     never a 500.

Configured via env OR the profile block — salient-core's resolve_config checks
the profile block first, then SALIENT_EMBED_* env. salient-tutor persists the
modal's values into the profile block (the override), so the "Both" model holds.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from salient_tutor import web
from salient_tutor.daemon import TutorDaemon


class _DaemonShell:
    """Bare object carrying just what the embed routes touch, bound to the real
    methods + a real KnowledgeGraph + a temp work_root (for the config file)."""

    embed_config = TutorDaemon.embed_config
    set_embed_config = TutorDaemon.set_embed_config
    _embed_backfill_once = TutorDaemon._embed_backfill_once

    def __init__(self, tmp_path, monkeypatch):
        from pathlib import Path

        from salient_core import KnowledgeGraph

        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        self.work_root = Path(tmp_path)
        self.profile: dict = {}
        self._embed_config_path = self.work_root / "embed_config.json"
        self.kg = KnowledgeGraph(tmp_path / "kg.db")


class TestEmbedConfigView:
    def test_inert_by_default(self, tmp_path, monkeypatch):
        for var in ("SALIENT_EMBED_BASE_URL", "SALIENT_EMBED_MODEL", "SALIENT_EMBED_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        shell = _DaemonShell(tmp_path, monkeypatch)
        cfg = shell.embed_config()
        assert cfg["enabled"] is False
        assert cfg["model"] == "" and cfg["api_key"] is False
        assert cfg["coverage"] == {}

    def test_env_vars_drive_config_when_no_profile_block(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIENT_EMBED_BASE_URL", "http://ai.home:1234")
        monkeypatch.setenv("SALIENT_EMBED_MODEL", "nomic-embed")
        shell = _DaemonShell(tmp_path, monkeypatch)
        cfg = shell.embed_config()
        assert cfg["enabled"] is True
        assert cfg["base_url"] == "http://ai.home:1234"
        assert cfg["model"] == "nomic-embed"


class TestSetEmbedConfig:
    def test_set_then_clear_persists_and_reverts(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        res = shell.set_embed_config(
            base_url="http://ai.home:1234", model="bge-large", api_key="sk-secret"
        )
        assert res["enabled"] is True
        assert res["base_url"] == "http://ai.home:1234" and res["model"] == "bge-large"
        # api_key is masked to a presence flag — the secret never comes back.
        assert res["api_key"] is True and "sk-secret" not in str(res)
        # Persisted to the file + the profile block.
        assert (tmp_path / "embed_config.json").exists()
        assert shell.profile["embeddings"]["model"] == "bge-large"

        # Clear: file removed, profile block dropped, back to inert.
        cleared = shell.set_embed_config(base_url="", model="", api_key="")
        assert cleared["enabled"] is False
        assert not (tmp_path / "embed_config.json").exists()
        assert "embeddings" not in shell.profile

    def test_partial_config_is_rejected(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        # base_url without a model is not a usable config.
        res = shell.set_embed_config(base_url="http://ai.home:1234", model="", api_key="")
        assert "error" in res
        assert shell.profile.get("embeddings") is None


class TestEmbedConfigRoutes:
    def test_get_and_post_routes(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        client = TestClient(web.app)

        assert client.get("/api/embed/config").json()["enabled"] is False
        r = client.post(
            "/api/embed/config",
            json={"base_url": "http://ai.home:1234", "model": "nomic"},
        )
        assert r.status_code == 200 and r.json()["enabled"] is True
        assert client.get("/api/embed/config").json()["model"] == "nomic"


class TestEmbedModelsFailSafe:
    """A down/unreachable embed server must NOT 500 the modal — it returns
    reachable:false so the UI can show a warning and the app keeps working."""

    def test_unreachable_returns_reachable_false(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        client = TestClient(web.app)
        # A bogus port that won't accept a connection within the short timeout.
        r = client.get("/api/embed/models", params={"base_url": "http://127.0.0.1:1"})
        assert r.status_code == 200
        body = r.json()
        assert body["reachable"] is False
        assert body["models"] == []
        assert "error" in body

    def test_no_base_url_and_no_config(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        client = TestClient(web.app)
        r = client.get("/api/embed/models")
        assert r.status_code == 200
        assert r.json()["reachable"] is False


class TestBackfillEmbedsPendingFacts:
    """The loop the operator daemon usually owns — here TutorDaemon runs it. A
    stubbed Embedder (no HTTP) proves facts lacking a vector get embedded."""

    def test_backfill_stores_vectors(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        # Configure a model + seed two facts that need embedding.
        shell.profile["embeddings"] = {"base_url": "http://x", "model": "stub-embed"}
        shell.kg.assert_fact("s1", "passage", "alpha", agent="test")
        shell.kg.assert_fact("s2", "passage", "beta", agent="test")
        total, embedded, pending = shell.kg.embedding_counts("stub-embed")
        assert (total, embedded, pending) == (2, 0, 2)

        # Stub get_embedder to return an Embedder whose .embed yields fixed vecs.
        from salient_core.memory import embeddings as emb

        fake = emb.Embedder(emb.EmbeddingConfig(model="stub-embed", base_url="http://x"))
        fake.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        with (
            patch.object(emb, "get_embedder", return_value=fake),
            patch("salient_core.get_embedder", return_value=fake),
        ):
            stored = asyncio_run(shell._embed_backfill_once())

        assert stored == 2
        _, embedded, pending = shell.kg.embedding_counts("stub-embed")
        assert (embedded, pending) == (2, 0)

    def test_backfill_inert_without_embedder(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.kg.assert_fact("s1", "passage", "alpha", agent="test")
        # No embeddings configured → backfill is a no-op, never raises.
        assert asyncio_run(shell._embed_backfill_once()) == 0


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
