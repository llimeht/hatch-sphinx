"""test hook function and configuration"""

from __future__ import annotations

from pathlib import Path

from .conftest import FixtureProject


def test_tool_build(new_project: FixtureProject, tmp_path: Path) -> None:
    """test sphinx 'build' tool"""

    new_project.add_tool_config(
        """\
[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "build"
source = "source"
out_dir = "output/html"
format = "html"
"""
    )

    (new_project.path / "docs" / "source").mkdir(exist_ok=True, parents=True)

    (new_project.path / "docs" / "source" / "conf.py").write_text(
        """\
project = 'Test Project'

extensions = [
  'sphinx.ext.autodoc',
]
html_theme = 'default'
html_static_path = ['_static']
    """
    )

    (new_project.path / "docs" / "source" / "index.rst").write_text(
        """\
Test Documentation
=====================

Contents
--------

**Test Project** is a Fake Python library.

.. toctree::
:maxdepth: 1


Indices and Search
------------------

* :ref:`genindex`
* :ref:`search`

"""
    )

    new_project.build()

    # Check that the file got created in the source tree
    assert (new_project.path / "docs" / "output" / "html" / "objects.inv").exists()
    assert (new_project.path / "docs" / "output" / "html" / "index.html").exists()

    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()

    with new_project.wheel() as whl:
        whl.extractall(extract_dir)
        # Check that the file made it into the wheel
        assert (extract_dir / "my-test-app" / "docs" / "html" / "index.html").exists()


def test_tool_apidoc(new_project: FixtureProject, tmp_path: Path) -> None:
    """test sphinx 'apiddoc' tool"""

    new_project.add_tool_config(
        """\
[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "apidoc"
out_dir = "output/api"
"""
    )

    (new_project.path / "docs").mkdir(exist_ok=True)

    new_project.build()

    # Check that the file got created in the source tree
    assert (new_project.path / "docs" / "output" / "api" / "modules.rst").exists()

    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()

    with new_project.wheel() as whl:
        whl.extractall(extract_dir)
        # Check that the file made it into the wheel
        assert (extract_dir / "my-test-app" / "docs" / "api" / "modules.rst").exists()


def test_tool_custom(new_project: FixtureProject, tmp_path: Path) -> None:
    """test 'custom' commands tool"""

    new_project.add_tool_config(
        """\
[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "custom"
out_dir = "output"
shell = true
commands = [
    "touch output/foo.html",
    "touch output/1\\\\ 2.html output/a1.html output/a2.html",
    "rm output/a*.html",
    ["touch", "output/3\\\\ 4.html", "output/b1.html", "output/b2.html"],
    ["rm", "output/b*.html"],
]

[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "custom"
out_dir = "output"
shell = false
commands = [
    ["touch", "output/1*.html"],
]
"""
    )

    (new_project.path / "docs").mkdir(exist_ok=True)

    new_project.build()

    # Check that the files got created in the source tree
    assert (new_project.path / "docs" / "output" / "foo.html").exists()

    # Check handling of multi-arg commands with spaces (shell=True)
    assert (new_project.path / "docs" / "output" / "1 2.html").exists()
    assert not (new_project.path / "docs" / "output" / "a1.html").exists()
    assert (new_project.path / "docs" / "output" / "3 4.html").exists()
    assert not (new_project.path / "docs" / "output" / "b1.html").exists()

    # And for shell=False where wildcards will not be expanded
    assert (new_project.path / "docs" / "output" / "1*.html").exists()

    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()

    with new_project.wheel() as whl:
        whl.extractall(extract_dir)
        # Check that the file made it into the wheel
        assert (extract_dir / "my-test-app" / "docs" / "foo.html").exists()
