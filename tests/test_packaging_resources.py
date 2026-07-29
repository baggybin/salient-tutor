"""Bundled resources resolve from the INSTALLED package, not the source tree.

Prompts, curricula, the pedagogy bundle and the web UI used to be resolved as
``Path(__file__).parents[2] / …``. That is the repo root in a checkout and
``<venv>/lib/python3.X`` once installed, and they were never packaged either —
``packages.find`` collects Python packages, and these lived at the repo root. So
a non-editable ``pip install salient-tutor`` produced a build that raised
``FileNotFoundError: …/python3.12/prompts/librarian.md`` and refused to mount its
own static directory at import time.

It stayed invisible because CI and the HOWTO both install with ``-e``, where the
broken path happens to be the right one.

Writable state is the mirror-image bug and is pinned here too: a workspace must
never resolve under site-packages.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from salient_tutor import resource_paths, state_paths

_REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# resources resolve inside the package
# ---------------------------------------------------------------------------


def test_resources_live_inside_the_package() -> None:
    """The whole fix in one assertion: not the repo root, the package."""
    import salient_tutor

    pkg = Path(salient_tutor.__file__).resolve().parent

    assert resource_paths.RESOURCES.is_relative_to(pkg), (
        f"resources resolved to {resource_paths.RESOURCES}, outside the package "
        f"({pkg}) — this is the checkout-relative lookup that breaks installs"
    )


@pytest.mark.parametrize(
    ("path", "what"),
    [
        (resource_paths.PROMPTS, "prompts"),
        (resource_paths.DATA, "data"),
        (resource_paths.WEB_STATIC, "web/static"),
    ],
)
def test_each_resource_tree_exists(path: Path, what: str) -> None:
    assert path.is_dir(), f"{what} missing at {path}"


@pytest.mark.parametrize(
    "relative",
    [
        "prompts/tutor.md",
        "prompts/librarian.md",
        "prompts/judge.md",
        "data/pedagogy_bundle.json",
        "web/static/index.html",
        "web/static/css/app.css",
    ],
)
def test_named_resources_are_present(relative: str) -> None:
    """The specific files whose absence produced the original crashes."""
    assert (resource_paths.RESOURCES / relative).is_file(), f"missing {relative}"


def test_curricula_are_bundled() -> None:
    assert list((resource_paths.DATA / "curricula").glob("*.json")), "no curricula packaged"


def test_no_checkout_relative_resource_lookups_remain() -> None:
    """Grep pin, straight from the plan's acceptance criteria.

    `parents[2]` / `parent.parent.parent` anywhere in the package means someone
    reintroduced a lookup that works in a checkout and breaks once installed.
    `state_paths` is the one legitimate user: it reads the LEGACY pointer, which
    by definition lives at the old repo-root location.
    """
    import io
    import tokenize

    def code_only(source: str) -> str:
        """Source with comments and string literals removed.

        Docstrings legitimately NAME the old broken pattern while explaining it;
        a plain substring grep would flag the explanation as the offence.
        """
        out: list[str] = []
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
        return " ".join(out)

    offenders: list[str] = []
    for py in (_REPO / "src" / "salient_tutor").rglob("*.py"):
        if py.name == "state_paths.py":
            continue
        code = code_only(py.read_text(encoding="utf-8"))
        if "parents [ 2 ]" in code or "parent . parent . parent" in code:
            offenders.append(str(py.relative_to(_REPO)))

    assert not offenders, f"checkout-relative resource lookups: {offenders}"


# ---------------------------------------------------------------------------
# packaging declaration
# ---------------------------------------------------------------------------


def test_package_data_declares_every_resource_tree() -> None:
    """Without this the trees exist in git and never reach the wheel."""
    cfg = tomllib.loads((_REPO / "pyproject.toml").read_text())
    declared = cfg["tool"]["setuptools"]["package-data"]["salient_tutor"]

    for tree in ("resources/prompts/**/*", "resources/data/**/*", "resources/web/**/*"):
        assert tree in declared, f"{tree} not declared as package data"


def test_platformdirs_is_declared() -> None:
    """State paths depend on it; an undeclared import breaks a clean install."""
    cfg = tomllib.loads((_REPO / "pyproject.toml").read_text())
    deps = " ".join(cfg["project"]["dependencies"])

    assert "platformdirs" in deps


def test_the_dead_stylesheet_is_gone() -> None:
    """`index.html` links `/css/app.css`; the root-level copy was dead weight."""
    assert not (resource_paths.WEB_STATIC / "app.css").exists()
    assert (resource_paths.WEB_STATIC / "css" / "app.css").is_file()


# ---------------------------------------------------------------------------
# writable state never lands in site-packages
# ---------------------------------------------------------------------------


def test_state_root_is_outside_the_package() -> None:
    import salient_tutor

    pkg = Path(salient_tutor.__file__).resolve().parent

    assert not state_paths.state_root().is_relative_to(pkg), (
        "workspaces would be written under site-packages — wrong home for a "
        "learner's work, and frequently not writable"
    )


def test_default_work_root_and_pointer_sit_under_the_state_root() -> None:
    root = state_paths.state_root()

    assert state_paths.default_work_root().is_relative_to(root)
    assert state_paths.pointer_path().is_relative_to(root)


def test_env_override_still_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TUTOR_WORK_ROOT", str(tmp_path))

    assert state_paths.resolve_env_work_root() == tmp_path.resolve()


def test_relative_env_override_resolves_against_state_not_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """So its meaning does not change with the launch directory."""
    monkeypatch.setenv("TUTOR_WORK_ROOT", "schoolbag")

    resolved = state_paths.resolve_env_work_root()

    assert resolved == (state_paths.state_root() / "schoolbag").resolve()


def test_absent_env_override_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TUTOR_WORK_ROOT", raising=False)

    assert state_paths.resolve_env_work_root() is None


def test_a_missing_resource_fails_loudly_and_names_itself() -> None:
    """A packaging fault should say so, not surface as an empty roster."""
    with pytest.raises(resource_paths.ResourceMissingError) as caught:
        resource_paths.require(resource_paths.RESOURCES / "nope", "the nope tree")

    assert "the nope tree" in str(caught.value)
    assert "incomplete" in str(caught.value)
