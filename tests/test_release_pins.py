"""Every hand-maintained version pin must name the version being released.

Debt item D-5: the reusable workflow carries a default install ref, and the
README and the deployment guide carry the tag an adopter is told to pin. None
of them fails when it is forgotten, so a release can ship a workflow that
installs the previous engine and a guide that points at a branch. Version
0.1.3 shipped with three such pins stale. These tests make forgetting loud.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from devostasis import __version__

ROOT = Path(__file__).resolve().parent.parent
TAG = f"v{__version__}"

# Files that document how to install or call a released version. CHANGELOG is
# excluded on purpose: it names every past version and must keep doing so.
PINNED_FILES = (
    Path(".github/workflows/observe-self.yml"),
    Path("README.md"),
    Path("docs/deployment.md"),
    Path(".github/workflows/work-observe.yml"),
    Path("examples/work/github-observe.yml"),
    Path("examples/work/gitlab-observe.yml"),
    Path(".github/workflows/work-operations.yml"),
    Path("examples/work/gitlab-operations.yml"),
)

WORKFLOW_REF = re.compile(r"(?:observe-self|work-observe|work-operations)\.yml@(v[0-9][^\s\"']*)")
# Case-insensitive and with the optional .git: GitHub resolves both spellings,
# so a pin written either way is a pin that must resolve.
INSTALL_REF = re.compile(r"github\.com/drevendev/devostasis(?:\.git)?@([^\s\"']+)", re.IGNORECASE)
DEFAULT_REF = re.compile(r"devostasis-ref:.*?\n(?:.*?\n)*?\s*default:\s*(\S+)", re.MULTILINE)


def test_the_package_version_and_the_module_agree():
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert declared == __version__, "pyproject.toml and devostasis.__version__ disagree"


@pytest.mark.parametrize("workflow_path", (".github/workflows/observe-self.yml", ".github/workflows/work-observe.yml", ".github/workflows/work-operations.yml"))
def test_the_reusable_workflow_installs_the_version_it_ships_with(workflow_path):
    """A caller pinning the workflow at this tag and passing no ref gets this engine."""
    workflow = (ROOT / workflow_path).read_text(encoding="utf-8")
    match = DEFAULT_REF.search(workflow)
    assert match, "observe-self.yml no longer declares a default devostasis-ref"
    assert match.group(1) == TAG, f"default devostasis-ref is {match.group(1)}, expected {TAG}"


@pytest.mark.parametrize("relative", PINNED_FILES, ids=lambda path: str(path))
def test_documented_pins_name_the_current_tag(relative: Path):
    """A literal ref must be this tag. A templated one (an expression, or the environment variable the workflow passes it through) resolves at run time and is left alone."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    for pattern, what in ((WORKFLOW_REF, "workflow pin"), (INSTALL_REF, "install ref")):
        for found in pattern.findall(text):
            if found.startswith("${"):
                continue
            assert found == TAG, f"{relative}: {what} {found} should be {TAG}"


@pytest.mark.parametrize("path", ("examples/work/gitlab-observe.yml", "examples/work/gitlab-operations.yml"))
def test_gitlab_install_default_names_the_current_tag(path):
    match = re.search(r'DEVOSTASIS_REF:\s*"([^"]+)"', (ROOT / path).read_text())
    assert match and match.group(1) == TAG


def test_the_changelog_has_a_section_for_this_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## {re.escape(__version__)}(\s|\()", changelog, re.MULTILINE), (
        f"CHANGELOG.md has no section for {__version__}"
    )
