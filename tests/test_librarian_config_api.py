"""Librarian provider config — the parser switch (Claude ↔ local LM Studio).

The librarian is the agent that reads + structures uploaded PDFs. By default it
runs on Claude; an operator can route it at a local chat endpoint (LM Studio
serving the Anthropic /v1/messages shape) so parsing is fully local. The
override is per-agent: only the librarian's SDK subprocess is rerouted
(ANTHROPIC_BASE_URL + --bare + thinking disabled); the tutor always stays on
Claude. Ported from salient-core's endpoint: block, focused to the librarian.

Covers:
  1. librarian_config() / set_librarian_config() — resolved view + persist/clear
     to work/librarian_config.json, with the api_key never echoed back.
  2. _make_options builds the per-agent endpoint override when local (env,
     --bare, thinking disabled, local model) and leaves the tutor untouched.
  3. Changing the config drops the cached librarian runner so the next prompt
     spawns a fresh subprocess with the new env.
  4. The GET/POST /api/librarian/config routes.
  5. /api/librarian/models fail-safe: an unreachable server returns
     reachable:false, never a 500.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from salient_tutor import web
from salient_tutor.daemon import TutorDaemon


class _DaemonShell:
    """Bare object carrying just what the librarian routes touch, bound to the
    real methods. _make_options is monkeypatched to stub make_bus so we test the
    endpoint-override logic without spawning SDK subprocesses."""

    librarian_config = TutorDaemon.librarian_config
    set_librarian_config = TutorDaemon.set_librarian_config
    agent_config = TutorDaemon.agent_config
    set_agent_config = TutorDaemon.set_agent_config
    _agent_endpoint_for = TutorDaemon._agent_endpoint_for
    _runtime_for = TutorDaemon._runtime_for
    _make_options = TutorDaemon._make_options
    _rebuild_runner = TutorDaemon._rebuild_runner
    _persist_agent_runtime = TutorDaemon._persist_agent_runtime
    _rebuild_librarian_runner = TutorDaemon._rebuild_librarian_runner

    def __init__(self, tmp_path, monkeypatch):
        from pathlib import Path

        monkeypatch.setenv("SALIENT_TUTOR_WORK_ROOT", str(tmp_path))
        self.work_root = Path(tmp_path)
        self._librarian_config_path = self.work_root / "librarian_config.json"
        self._agent_config_path = self.work_root / "agent_configs.json"
        self._agent_runtime: dict = {}
        self._tasks: list = []
        # _make_options reads agent_configs + _agent_runtime + _load_prompt;
        # give it a minimal roster. make_bus is stubbed below per-test.
        self.agent_configs = {
            "librarian": {
                "system_prompt_file": "librarian.md",
                "model": "claude-x",
                "builtin_tools": ["Read"],
                "bus_tools": False,
                "max_turns": 20,
            },
            "tutor": {
                "system_prompt_file": "tutor.md",
                "model": "claude-opus",
                "builtin_tools": ["WebSearch", "WebFetch"],
                "max_turns": 30,
            },
        }
        self.runners: dict = {}


class TestLibrarianConfigView:
    def test_default_is_claude(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        cfg = shell.librarian_config()
        assert cfg["provider"] == "claude"
        assert cfg["model"] == "" and cfg["api_key"] is False
        # No endpoint override when on Claude (anthropic).
        assert shell._agent_endpoint_for("librarian") is None

    def test_set_local_resolves_endpoint(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        res = shell.set_librarian_config(
            provider="local",
            base_url="http://ai.home:1234",
            model="ornith-1.0-35b",
            api_key="lm-studio",
        )
        assert res["provider"] == "local"
        assert res["base_url"] == "http://ai.home:1234" and res["model"] == "ornith-1.0-35b"
        # api_key masked to a presence flag — the secret never comes back.
        assert res["api_key"] is True and "lm-studio" not in str(res)
        # The override tuple resolves with the configured values.
        ep = shell._agent_endpoint_for("librarian")
        assert ep is not None
        assert ep[0] == "http://ai.home:1234" and ep[1] == "ornith-1.0-35b"

    def test_local_requires_base_url_and_model(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        res = shell.set_librarian_config(provider="local", base_url="http://x", model="")
        assert "error" in res
        assert shell._agent_runtime.get("librarian", {}).get("provider") != "local"

    def test_unknown_provider_rejected(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        res = shell.set_librarian_config(provider="gemini", base_url="x", model="y")
        assert "error" in res

    def test_clear_reverts_to_claude_and_removes_file(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.set_librarian_config(provider="local", base_url="http://x", model="y")
        res = shell.set_librarian_config(provider="claude")
        assert res["provider"] == "claude"
        # The new per-agent file is gone (and the legacy one never persists).
        assert not (tmp_path / "agent_configs.json").exists()
        assert not (tmp_path / "librarian_config.json").exists()
        assert shell._agent_endpoint_for("librarian") is None


class TestMakeOptionsEndpointOverride:
    """The crux: when the librarian is local, _make_options injects the
    per-agent endpoint env + --bare + disabled thinking, and swaps in the local
    model. The tutor is never rerouted."""

    def _options(self, shell, agent, monkeypatch):
        # Stub make_bus (returns (server, name, wire_names)) + _load_prompt so
        # _make_options runs without the full daemon/SDK stack.
        monkeypatch.setattr("salient_tutor.daemon.make_bus", lambda d, a: (None, "bus", []))
        shell._load_prompt = lambda a: "prompt"
        return shell._make_options(agent)

    def test_local_librarian_gets_endpoint_override(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.set_librarian_config(
            provider="local",
            base_url="http://ai.home:1234",
            model="ornith-1.0-35b",
            api_key="lm-studio",
            auth_style="bearer",
        )
        opts = self._options(shell, "librarian", monkeypatch)
        assert opts.env["ANTHROPIC_BASE_URL"] == "http://ai.home:1234"
        # bearer auth → AUTH_TOKEN set, API_KEY cleared.
        assert opts.env.get("ANTHROPIC_AUTH_TOKEN") == "lm-studio"
        assert "ANTHROPIC_API_KEY" not in opts.env
        assert opts.env["CLAUDE_CODE_ATTRIBUTION_HEADER"] == "0"
        assert opts.model == "ornith-1.0-35b"  # local model, not the Claude default
        assert opts.extra_args.get("bare") is None  # --bare passed
        assert opts.thinking == {"type": "disabled"}  # thinking off (local can't stream it)

    def test_local_librarian_api_key_auth(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.set_librarian_config(
            provider="local", base_url="http://x", model="m", api_key="k", auth_style="api_key"
        )
        opts = self._options(shell, "librarian", monkeypatch)
        assert opts.env.get("ANTHROPIC_API_KEY") == "k"
        assert "ANTHROPIC_AUTH_TOKEN" not in opts.env

    def test_claude_librarian_has_no_override(self, tmp_path, monkeypatch):
        # Default (Claude): no env override, original model, no --bare.
        shell = _DaemonShell(tmp_path, monkeypatch)
        opts = self._options(shell, "librarian", monkeypatch)
        assert opts.env is None or "ANTHROPIC_BASE_URL" not in (opts.env or {})
        assert opts.model == "claude-x"  # the roster default, unchanged
        assert not (opts.extra_args or {})

    def test_tutor_is_never_rerouted(self, tmp_path, monkeypatch):
        # Even with the librarian on local, the tutor stays on Claude.
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.set_librarian_config(provider="local", base_url="http://ai.home:1234", model="ornith")
        opts = self._options(shell, "tutor", monkeypatch)
        assert opts.env is None or "ANTHROPIC_BASE_URL" not in (opts.env or {})
        assert opts.model == "claude-opus"
        assert not (opts.extra_args or {})

    def test_builtin_tools_are_registered_and_allowed(self, tmp_path, monkeypatch):
        # Regression: built-in tools (e.g. Read) must be in `tools`, not only
        # allowed_tools. allowed_tools just auto-approves already-registered
        # tools; under --bare (local librarian) the default built-in toolset
        # isn't loaded, so Read would be "No such tool available" unless it's
        # explicitly registered via `tools`.
        shell = _DaemonShell(tmp_path, monkeypatch)
        opts = self._options(shell, "librarian", monkeypatch)
        assert opts.tools == ["Read"]
        assert "Read" in opts.allowed_tools


class TestRunnerRebuiltOnChange:
    """set_librarian_config drops the cached librarian runner so the next
    _make_runner call rebuilds it with the new endpoint env (the SDK binds env
    at subprocess spawn)."""

    def test_runner_dropped_on_switch(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.runners["librarian"] = object()  # pretend a runner exists
        shell.set_librarian_config(provider="local", base_url="http://x", model="m")
        assert "librarian" not in shell.runners  # dropped → next prompt rebuilds

    def test_rebuild_safe_when_no_runner(self, tmp_path, monkeypatch):
        # No runner yet (fresh daemon) — switching must not error.
        shell = _DaemonShell(tmp_path, monkeypatch)
        shell.set_librarian_config(provider="local", base_url="http://x", model="m")
        assert "librarian" not in shell.runners


class TestLibrarianConfigRoutes:
    def test_get_default_and_post_local(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        client = TestClient(web.app)
        assert client.get("/api/librarian/config").json()["provider"] == "claude"
        r = client.post(
            "/api/librarian/config",
            json={
                "provider": "local",
                "base_url": "http://ai.home:1234",
                "model": "ornith-1.0-35b",
            },
        )
        assert r.status_code == 200 and r.json()["provider"] == "local"
        assert client.get("/api/librarian/config").json()["model"] == "ornith-1.0-35b"


class TestLibrarianModelsFailSafe:
    """A down/unreachable parser server must NOT 500 the modal — returns
    reachable:false so the UI warns and the operator stays on Claude."""

    def test_unreachable_returns_reachable_false(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        client = TestClient(web.app)
        r = client.get("/api/librarian/models", params={"base_url": "http://127.0.0.1:1"})
        assert r.status_code == 200
        body = r.json()
        assert body["reachable"] is False
        assert body["anthropic"] is False
        assert body["models"] == []

    def test_no_base_url(self, tmp_path, monkeypatch):
        shell = _DaemonShell(tmp_path, monkeypatch)
        monkeypatch.setattr(web, "daemon", shell)
        client = TestClient(web.app)
        r = client.get("/api/librarian/models")
        assert r.status_code == 200
        assert r.json()["reachable"] is False
