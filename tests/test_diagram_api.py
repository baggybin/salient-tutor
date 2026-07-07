"""Server-side diagram rendering — salient_tutor.diagrams + POST /api/diagram.

Unit-tests the render() contract (unknown/disabled engine, oversize, sanitizer,
capability probe) without needing any binary, plus binary-backed happy-path and
PlantUML-sandbox tests that SKIP when the engine isn't installed/enabled. The
endpoint tests use TestClient without the lifespan (no daemon needed — the route
doesn't touch it), mirroring test_quiz_api.py.

No pytest-asyncio in this repo — coroutines run via asyncio.run.
"""

from __future__ import annotations

import asyncio
import shutil

import pytest
from fastapi.testclient import TestClient

from salient_tutor import diagrams, web

_HAS_DOT = shutil.which("dot") is not None
_HAS_D2 = shutil.which("d2") is not None
_HAS_PLANTUML = shutil.which("plantuml") is not None


# ── render() — contract paths that need no binary ────────────────────────────
def test_unknown_engine_is_rejected():
    svg, err = asyncio.run(diagrams.render("nope", "a -> b"))
    assert svg is None
    assert "unsupported" in err.lower()


def test_empty_source_is_rejected():
    svg, err = asyncio.run(diagrams.render("dot", "   "))
    assert svg is None
    assert "empty" in err.lower()


def test_oversize_source_is_rejected():
    svg, err = asyncio.run(diagrams.render("dot", "x" * (diagrams._MAX_SRC + 1)))
    assert svg is None
    assert "too large" in err.lower()


def test_plantuml_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TUTOR_DIAGRAM_PLANTUML", raising=False)
    svg, err = asyncio.run(diagrams.render("plantuml", "@startuml\na->b\n@enduml"))
    assert svg is None
    assert "disabled" in err.lower()


def test_plantuml_source_gets_dark_theme_injected():
    themed = diagrams._themed_source("plantuml", "@startuml\nAlice->Bob\n@enduml")
    lines = themed.split("\n")
    assert lines[0] == "@startuml"
    assert lines[1] == f"!theme {diagrams._PLANTUML_THEME}"  # right after @start


def test_plantuml_authors_theme_is_not_overridden():
    src = "@startuml\n!theme spacelab\nA->B\n@enduml"
    assert diagrams._themed_source("plantuml", src) == src  # untouched


def test_dot_source_is_not_mutated_by_theming():
    # dot is themed via argv flags, not source injection.
    assert diagrams._themed_source("dot", "digraph{a->b}") == "digraph{a->b}"


def test_sanitizer_strips_script_and_handlers():
    dirty = '<svg><script>alert(1)</script><rect onclick="x()" width="1"/></svg>'
    clean = diagrams._sanitize_svg(dirty)
    assert "<script" not in clean.lower()
    assert "onclick" not in clean.lower()
    assert "<rect" in clean.lower()  # structure preserved


def test_available_engines_reports_plantuml_gate(monkeypatch):
    monkeypatch.delenv("TUTOR_DIAGRAM_PLANTUML", raising=False)
    engines = diagrams.available_engines()
    assert set(engines) == {"dot", "d2", "plantuml"}
    # plantuml is False whenever it's not explicitly enabled, regardless of binary
    assert engines["plantuml"] is False
    monkeypatch.setenv("TUTOR_DIAGRAM_PLANTUML", "1")
    if _HAS_PLANTUML:
        assert diagrams.available_engines()["plantuml"] is True


# ── render() — binary-backed happy paths (skip when engine absent) ───────────
@pytest.mark.skipif(not _HAS_DOT, reason="graphviz `dot` not installed")
def test_dot_renders_svg():
    svg, err = asyncio.run(diagrams.render("dot", "digraph{a->b}"))
    assert err is None
    assert svg.lstrip().startswith("<svg")


@pytest.mark.skipif(not _HAS_DOT, reason="graphviz `dot` not installed")
def test_dot_is_dark_themed():
    # The default-attr flags skin an un-styled diagram to the dark palette.
    svg, err = asyncio.run(diagrams.render("dot", "digraph{a->b}"))
    assert err is None
    assert diagrams._C_NODE_FILL in svg  # node fill = --bg-3
    assert diagrams._C_PANE_TEXT in svg  # label text = --text


@pytest.mark.skipif(not _HAS_D2, reason="`d2` not installed")
def test_d2_renders_svg():
    svg, err = asyncio.run(diagrams.render("d2", "a -> b"))
    assert err is None
    assert "<svg" in svg


@pytest.mark.skipif(not _HAS_DOT, reason="graphviz `dot` not installed")
def test_dot_syntax_error_returns_error_not_svg():
    svg, err = asyncio.run(diagrams.render("dot", "digraph{ this is not valid"))
    assert svg is None
    assert err  # stderr tail surfaced for the repair button


@pytest.mark.skipif(not _HAS_PLANTUML, reason="`plantuml` not installed")
def test_plantuml_sandbox_blocks_local_include(monkeypatch, tmp_path):
    monkeypatch.setenv("TUTOR_DIAGRAM_PLANTUML", "1")
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET_CONTENT_12345")
    src = f"@startuml\n!include {secret}\nAlice->Bob\n@enduml"
    svg, err = asyncio.run(diagrams.render("plantuml", src))
    # Either the include is refused (err) or it renders without leaking the file;
    # the one thing that must never happen is the secret reaching the output.
    assert "SECRET_CONTENT_12345" not in (svg or "")


# ── POST /api/diagram + /api/config ──────────────────────────────────────────
def test_endpoint_unknown_engine_returns_error():
    resp = TestClient(web.app).post("/api/diagram", json={"engine": "nope", "source": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["svg"] is None
    assert body["error"]


@pytest.mark.skipif(not _HAS_DOT, reason="graphviz `dot` not installed")
def test_endpoint_dot_returns_svg():
    resp = TestClient(web.app).post(
        "/api/diagram", json={"engine": "dot", "source": "digraph{a->b}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert "<svg" in body["svg"]


def test_config_exposes_diagram_engines(monkeypatch):
    monkeypatch.setattr(web, "daemon", None)  # exercise the no-daemon branch too
    body = TestClient(web.app).get("/api/config").json()
    assert "diagram_engines" in body
    assert body["diagram_engines"]["mermaid"] is True
    assert set(body["diagram_engines"]) >= {"mermaid", "dot", "d2", "plantuml"}
