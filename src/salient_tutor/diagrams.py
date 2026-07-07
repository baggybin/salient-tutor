"""Server-side diagram rendering — shells out to local engine binaries.

The tutor can emit fenced diagram source in one of several dialects; this module
renders the non-Mermaid ones (``dot`` / ``d2`` / ``plantuml``) to inline SVG via
the engine's CLI. Mermaid is deliberately NOT here — it renders client-side in
the browser (its CLI needs node + headless chromium), so keeping it there costs
nothing and avoids a heavy server dependency.

Hardening (this is a local-first app, but the render path still shells out):
  * source is passed on **stdin, never argv** — no shell, no interpolation;
  * every call is bounded by a source-size cap + a wall-clock timeout (killed);
  * output SVG is sanitized (``<script>`` / ``on*=`` stripped) before it's
    handed back for innerHTML injection;
  * **PlantUML** can read local files / fetch URLs via ``!include`` (SSRF +
    local-file-read); it runs under ``PLANTUML_SECURITY_PROFILE=SANDBOX`` which
    blocks that, and is **off by default** (opt in with
    ``TUTOR_DIAGRAM_PLANTUML=1``) until the sandbox is verified on a given host.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from contextlib import suppress

# Dark-UI palette (mirrors web/static/css/app.css :root) so server-rendered
# diagrams match the pane instead of arriving as dated black-on-white. Mermaid
# gets theme:"dark" client-side; these are the equivalent for the CLI engines.
_C_PANE_TEXT = "#e6edf3"  # --text
_C_NODE_FILL = "#1c2330"  # --bg-3
_C_NODE_LINE = "#818cf8"  # --accent (indigo node borders)
_C_EDGE = "#8b949e"  # --text-dim (edges + edge labels)
_C_FONT = "Helvetica"

# engine → argv. Each reads diagram source on stdin and writes SVG to stdout.
# The theming flags set DEFAULT graph/node/edge attributes — an explicit color
# in the author's source still wins, so this only skins un-styled diagrams.
_ENGINES: dict[str, list[str]] = {
    "dot": [
        "dot",
        "-Tsvg",
        "-Gbgcolor=transparent",
        f"-Gfontname={_C_FONT}",
        f"-Gfontcolor={_C_PANE_TEXT}",
        "-Nstyle=filled",
        f"-Nfillcolor={_C_NODE_FILL}",
        f"-Ncolor={_C_NODE_LINE}",
        f"-Nfontname={_C_FONT}",
        f"-Nfontcolor={_C_PANE_TEXT}",
        f"-Ecolor={_C_EDGE}",
        f"-Efontname={_C_FONT}",
        f"-Efontcolor={_C_EDGE}",
        "-Earrowsize=0.8",
    ],
    # Theme 200 = "Dark Mauve", a cohesive dark theme close to the app's accents.
    "d2": ["d2", "--theme", "200", "-", "-"],
    "plantuml": ["plantuml", "-tsvg", "-pipe", "-Djava.awt.headless=true"],
}

# PlantUML has no default-attr flags, so its dark theme is injected into the
# source instead (see _themed_source). "cyborg" is a built-in dark theme.
_PLANTUML_THEME = "cyborg"


def _themed_source(engine: str, source: str) -> str:
    """Apply per-engine theming that can't be set via argv. For PlantUML, inject
    a dark ``!theme`` right after the opening ``@start…`` directive — unless the
    author already picked a theme. dot/d2 are themed via their argv flags, so
    this is a no-op for them."""
    if engine != "plantuml" or "!theme" in source:
        return source
    lines = source.split("\n")
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("@start"):
            lines.insert(i + 1, f"!theme {_PLANTUML_THEME}")
            return "\n".join(lines)
    return source


# PlantUML's include/URL directives are an SSRF + local-file-read vector; the
# SANDBOX profile forbids them. Set via env (robust across the plantuml wrapper
# scripts, where -D ordering relative to -jar is brittle).
_PLANTUML_SANDBOX_ENV = {"PLANTUML_SECURITY_PROFILE": "SANDBOX"}

_MAX_SRC = 20_000  # reject oversize source before spawning anything
_TIMEOUT = 8.0  # seconds — hard-killed past this

_SVG_SCRIPT_RE = re.compile(r"<script\b[\s\S]*?</script\s*>", re.IGNORECASE)
_SVG_ON_ATTR_RE = re.compile(r"""\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)


def _plantuml_enabled() -> bool:
    return (os.environ.get("TUTOR_DIAGRAM_PLANTUML") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def available_engines() -> dict[str, bool]:
    """Map engine → renderable-here (binary on PATH and, for plantuml, enabled).

    Drives the client's engine toggle: an engine that's missing or disabled is
    grayed out rather than offered and then failing at render time."""
    out: dict[str, bool] = {}
    for name, argv in _ENGINES.items():
        ok = shutil.which(argv[0]) is not None
        if name == "plantuml":
            ok = ok and _plantuml_enabled()
        out[name] = ok
    return out


def _sanitize_svg(svg: str) -> str:
    """Strip active content from rendered SVG before innerHTML injection.

    Graphviz/d2/plantuml don't emit scripts for our inputs, but the output is
    injected as HTML, so belt-and-suspenders: drop ``<script>`` blocks and inline
    ``on*=`` event handlers."""
    svg = _SVG_SCRIPT_RE.sub("", svg)
    svg = _SVG_ON_ATTR_RE.sub("", svg)
    return svg


async def render(engine: str, source: str) -> tuple[str | None, str | None]:
    """Render ``source`` with ``engine`` → ``(svg, None)`` on success or
    ``(None, error)`` on any failure. Never raises for expected failures
    (unknown/disabled engine, missing binary, oversize, timeout, non-zero exit);
    the caller surfaces ``error`` to the client, which shows the same parse-error
    card + repair button it uses for Mermaid."""
    engine = (engine or "").strip().lower()
    argv = _ENGINES.get(engine)
    if argv is None:
        return None, f"unsupported diagram engine: {engine!r}"
    if engine == "plantuml" and not _plantuml_enabled():
        return None, "plantuml rendering is disabled on this server"

    # Cheap source validation first — independent of whether the engine binary is
    # installed, so an empty/oversize source is reported as such on any host.
    source = source or ""
    if not source.strip():
        return None, "empty diagram source"
    if len(source) > _MAX_SRC:
        return None, f"diagram source too large ({len(source)} > {_MAX_SRC} chars)"

    if shutil.which(argv[0]) is None:
        return None, f"{argv[0]} is not installed on this server"

    env = dict(os.environ)
    if engine == "plantuml":
        env.update(_PLANTUML_SANDBOX_ENV)

    themed = _themed_source(engine, source)

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except OSError as e:
        return None, f"failed to launch {argv[0]}: {e}"

    try:
        out, err = await asyncio.wait_for(proc.communicate(themed.encode()), _TIMEOUT)
    except TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
        with suppress(Exception):
            await proc.wait()
        return None, f"diagram render timed out after {_TIMEOUT:.0f}s"

    if proc.returncode != 0:
        tail = (err.decode(errors="replace").strip() or "render failed")[-500:]
        return None, tail

    svg = out.decode(errors="replace")
    start = svg.find("<svg")
    if start == -1:
        return None, "engine produced no SVG output"
    return _sanitize_svg(svg[start:]), None
