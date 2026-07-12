"""Runner construction through core's provider-neutral backend_factory seam.

Core's AgentRunner lost its ``options=`` field when the codex provider landed
(salient-core #52) — runners are now built from a zero-arg backend factory.
These tests pin the tutor's side of that contract: the claude/endpoint path
produces a LocalClaudeBackend factory over the assembled options, and a
``provider: codex`` runtime block routes through salient-core's CodexProvider
(stubbed here so the suite never needs the openai-codex SDK) with the
fail-closed approval policy.
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

import pytest
from claude_agent_sdk import ClaudeAgentOptions
from salient_core import (
    EventHub,
    LocalClaudeBackend,
    ProviderRegistry,
    reset_provider_registry,
    set_provider_registry,
)
from salient_core.codex import ApprovalDecision, CodexProvider

from salient_tutor.daemon import TutorDaemon


class _RunnerShell:
    """Bare daemon with just enough surface bound to drive _make_runner."""

    _make_runner = TutorDaemon._make_runner
    _make_options = TutorDaemon._make_options
    _make_codex_backend_factory = TutorDaemon._make_codex_backend_factory
    _make_codex_approval_handler = TutorDaemon._make_codex_approval_handler
    _load_prompt = TutorDaemon._load_prompt
    _agent_endpoint_for = TutorDaemon._agent_endpoint_for
    _runtime_for = TutorDaemon._runtime_for
    add_question = TutorDaemon.add_question

    def __init__(self, tmp_path) -> None:
        self.work_root = Path(tmp_path)
        self._agent_runtime: dict = {}
        self.context = None
        self.event_hub = EventHub()
        self.runners: dict = {}
        self.questions: list = []
        # librarian: bus_tools=False keeps _make_options / the codex factory
        # off make_bus, so the shell doesn't need the full DaemonServices
        # surface.
        self.agent_configs = {
            "librarian": {
                "system_prompt_file": "librarian.md",
                "model": "claude-sonnet-5[1m]",
                "builtin_tools": ["Read"],
                "bus_tools": False,
                "max_turns": 20,
            },
        }

        class _Inbox:
            def __init__(self, sink: list) -> None:
                self._sink = sink

            def add(self, *, agent: str, text: str, job_id=None) -> int:
                self._sink.append((agent, text))
                return len(self._sink)

        self.inbox = _Inbox(self.questions)


class _StubCodexProvider(CodexProvider):
    """CodexProvider whose create_backend records its arguments instead of
    touching the openai-codex SDK (which the test env may not have)."""

    def __init__(self) -> None:
        self.calls: list = []

    def create_backend(self, config, *, tool_bundle=None, **kwargs):
        self.calls.append({"config": dict(config), "tool_bundle": tool_bundle, **kwargs})
        return object()  # stand-in backend; never driven in these tests


@pytest.fixture
def stub_codex_provider():
    provider = _StubCodexProvider()
    set_provider_registry(ProviderRegistry([provider]))
    yield provider
    reset_provider_registry()


class TestClaudeBackendFactory:
    def test_anthropic_agent_gets_local_claude_backend_factory(self, tmp_path):
        shell = _RunnerShell(tmp_path)
        runner = shell._make_runner("librarian")
        assert isinstance(runner.backend_factory, partial)
        assert runner.backend_factory.func is LocalClaudeBackend
        (options,) = runner.backend_factory.args
        assert isinstance(options, ClaudeAgentOptions)
        assert options.model == "claude-sonnet-5[1m]"
        # The factory is zero-arg — the runner can call it as-is.
        backend = runner.backend_factory()
        assert isinstance(backend, LocalClaudeBackend)

    def test_runner_is_cached_and_wired_to_daemon(self, tmp_path):
        shell = _RunnerShell(tmp_path)
        runner = shell._make_runner("librarian")
        assert shell.runners["librarian"] is runner
        assert shell._make_runner("librarian") is runner
        assert runner._daemon is shell
        assert runner._event_hub is shell.event_hub


class TestCodexBackendFactory:
    def test_codex_agent_routes_through_provider_backend(self, tmp_path, stub_codex_provider):
        shell = _RunnerShell(tmp_path)
        shell._agent_runtime["librarian"] = {"provider": "codex", "effort": "med"}
        runner = shell._make_runner("librarian")
        # Not the claude path — a dedicated factory closure, no options partial.
        assert not isinstance(runner.backend_factory, partial)

        async def build():
            return runner.backend_factory()

        asyncio.run(build())
        (call,) = stub_codex_provider.calls
        config = call["config"]
        assert config["agent_name"] == "librarian"
        assert config["cwd"] == str(shell.work_root)
        # The same assembled system prompt the claude path would use.
        assert config["instructions"] == shell._load_prompt("librarian")
        # Roster tier (sonnet) maps to the codex counterpart; med → medium.
        assert config["model"] == "gpt-5.4"
        assert config["effort"] == "medium"
        assert call["approval_handler"] is not None
        # librarian has bus_tools=False → empty bundle handed to the gateway.
        assert not call["tool_bundle"].tools

    def test_codex_explicit_model_and_effort_win(self, tmp_path, stub_codex_provider):
        shell = _RunnerShell(tmp_path)
        shell._agent_runtime["librarian"] = {
            "provider": "codex",
            "model": "gpt-5.5",
            "effort": "high",
        }
        runner = shell._make_runner("librarian")

        async def build():
            return runner.backend_factory()

        asyncio.run(build())
        (call,) = stub_codex_provider.calls
        assert call["config"]["model"] == "gpt-5.5"
        assert call["config"]["effort"] == "high"


class TestCodexApprovalPolicy:
    """Fail-closed and scoped by the agent's own tool whitelist: read-only
    commands auto-accept only for agents whose builtin_tools already grant
    unconfined reads on the claude path (Bash, or Read without
    confine_reads_to_study); everything else declines and files an
    informational inbox note (the tutor has no answer surface)."""

    class _Request:
        def __init__(self, kind: str, params: dict) -> None:
            from salient_core.codex import ApprovalKind

            self.kind = ApprovalKind(kind)
            self.params = params
            self.method = f"item/{kind}/requestApproval"

    def _decide(self, shell, request, agent: str = "librarian"):
        async def scenario():
            handler = shell._make_codex_approval_handler(agent, asyncio.get_running_loop())
            decision = handler(request)
            await asyncio.sleep(0)  # flush call_soon_threadsafe inbox notes
            return decision

        return asyncio.run(scenario())

    def test_read_only_command_auto_accepts_for_unconfined_reader(self, tmp_path):
        # The shell librarian carries builtin_tools=["Read"] with no
        # confine_reads_to_study — the claude path could read anywhere, so
        # codex read-only shell is not a capability widening.
        shell = _RunnerShell(tmp_path)
        request = self._Request("command", {"command": ["git", "status", "--short"]})
        assert self._decide(shell, request) is ApprovalDecision.ACCEPT
        assert shell.questions == []

    def test_read_only_command_auto_accepts_for_bash_agent(self, tmp_path):
        shell = _RunnerShell(tmp_path)
        shell.agent_configs["librarian"]["builtin_tools"] = ["Bash"]
        request = self._Request("command", {"command": ["rg", "-n", "prereq", "notes"]})
        assert self._decide(shell, request) is ApprovalDecision.ACCEPT
        assert shell.questions == []

    def test_read_only_command_declines_for_confined_reader(self, tmp_path):
        # The real roster librarian has confine_reads_to_study=True; codex's
        # classifier passes positional paths unrestricted, so auto-accepting
        # would widen a study-confined Read into whole-disk enumeration.
        shell = _RunnerShell(tmp_path)
        shell.agent_configs["librarian"]["confine_reads_to_study"] = True
        request = self._Request("command", {"command": ["grep", "-r", "password", "/home"]})
        assert self._decide(shell, request) is ApprovalDecision.DECLINE
        ((agent, text),) = shell.questions
        assert agent == "librarian"
        assert text.startswith("[codex declined] command:")

    def test_read_only_command_declines_for_agent_without_file_tools(self, tmp_path):
        # builtin_tools=[] (judge, deepseek-routed tutors) had NO file access
        # on the claude path — codex must not grant a read-only shell.
        shell = _RunnerShell(tmp_path)
        shell.agent_configs["librarian"]["builtin_tools"] = []
        request = self._Request("command", {"command": ["cat", "/etc/hostname"]})
        assert self._decide(shell, request) is ApprovalDecision.DECLINE
        ((_, text),) = shell.questions
        assert text.startswith("[codex declined] command:")
        assert "cat" in text

    def test_write_command_declines_with_inbox_note(self, tmp_path):
        shell = _RunnerShell(tmp_path)
        request = self._Request("command", {"command": ["rm", "-rf", "notes"]})
        assert self._decide(shell, request) is ApprovalDecision.DECLINE
        ((agent, text),) = shell.questions
        assert agent == "librarian"
        assert text.startswith("[codex declined] command:")
        assert "rm" in text

    def test_file_change_declines(self, tmp_path):
        shell = _RunnerShell(tmp_path)
        request = self._Request("file_change", {"reason": "edit prompts/tutor.md"})
        assert self._decide(shell, request) is ApprovalDecision.DECLINE
        ((_, text),) = shell.questions
        assert "[codex declined] file_change:" in text


class TestSubmitTurnBudget:
    """Submits carry cfg max_turns as max_turns_hint: claude backends enforce
    the cap natively via ClaudeAgentOptions, but backend-seam providers
    (codex) rely on the runner's wire-level hard cap, which only arms when the
    job carries a budget."""

    def test_prompt_passes_cfg_max_turns_as_hint(self, tmp_path):
        shell = _RunnerShell(tmp_path)

        class _FakeJob:
            result = "ok"
            error = None

        class _FakeRunner:
            status = "idle"
            cfg = shell.agent_configs["librarian"]

            def __init__(self) -> None:
                self.submit_kwargs: dict = {}

            def submit(self, message, *, future, **kwargs):
                self.submit_kwargs = kwargs
                future.set_result(_FakeJob())

        fake = _FakeRunner()
        shell._make_runner = lambda agent: fake  # type: ignore[method-assign]
        reply = asyncio.run(TutorDaemon.prompt(shell, "librarian", "hi"))
        assert reply == "ok"
        assert fake.submit_kwargs == {"max_turns_hint": 20}
