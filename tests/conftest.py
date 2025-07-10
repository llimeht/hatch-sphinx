"""pytest fixtures for hatch-sphinx"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Generator
import zipfile

import pytest


@pytest.fixture(scope="session")
def plugin_path() -> Generator[Path, None, None]:
    """make a copy of the hatch-sphinx plugin for testing

    See https://hatch.pypa.io/latest/how-to/plugins/testing-builds/
    """
    with TemporaryDirectory() as d:
        directory = Path(d, "plugin")
        shutil.copytree(Path.cwd(), directory, ignore=shutil.ignore_patterns(".git"))

        yield directory.resolve()


@pytest.fixture
def new_project(
    tmp_path: Path,
    plugin_path: Path,  # pylint: disable=redefined-outer-name
) -> FixtureProject:
    """create a new Python project as a fixture"""
    project_dir = tmp_path / "my-test-app"
    project_dir.mkdir()

    project = FixtureProject(project_dir)

    project.pyproject.write_text(
        f"""\
[build-system]
requires = ["hatchling", "hatch-sphinx @ {plugin_path.as_uri()}"]
build-backend = "hatchling.build"

[project]
name = "my-test-app"
version = "0.1.1"

[tool.hatch]
verbose = true
#
# [tool.hatch.build.targets.wheel]
# artifacts = [
#     "docs/output",
# ]

[tool.hatch.build.targets.wheel.force-include]
"docs/output" = "my-test-app/docs"
""",
        encoding="utf-8",
    )

    package_dir = project_dir / "src" / "my_test_app"
    package_dir.mkdir(parents=True)

    package_root = package_dir / "__init__.py"
    package_root.write_text("")

    return project


class FixtureProject:
    """Python project ready for building as a test fixture"""

    def __init__(self, path: Path) -> None:
        """Create project in the specified path"""
        self.path = path

    @property
    def pyproject(self) -> Path:
        """Path to the pyproject.toml file for this project"""
        return self.path / "pyproject.toml"

    def add_tool_config(self, toolconf: str) -> None:
        """merge config snippet with generic project"""
        with open(self.pyproject, "ta", encoding="UTF-8") as fh:
            fh.write("\n")
            fh.write(toolconf)

    def build(self) -> None:
        """Attempt to build the project"""
        subprocess.run(
            # [sys.executable, "-m", "hatchling", "build"],
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--skip-dependency-check",
                "--wheel",
                "--config-setting",
                "display_debug=true",
            ],
            check=True,
            cwd=self.path,
        )

    @contextmanager
    def wheel(self) -> Iterator[zipfile.ZipFile]:
        """Find the build output (wheel)"""
        files = list((self.path / "dist").glob("*.whl"))
        assert len(files) == 1
        with zipfile.ZipFile(str(files[0])) as whl:
            yield whl
