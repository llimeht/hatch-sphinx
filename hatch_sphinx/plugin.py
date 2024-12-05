"""hatch-sphinx: hatchling build plugin for Sphinx document system

"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import MISSING, asdict, dataclass, field, fields
import logging
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
from typing import Any, Optional

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.config import BuilderConfig


log = logging.getLogger(__name__)
log_level = logging.getLevelName(os.getenv("HATCH_SPHINX_LOG_LEVEL", "INFO"))
log.setLevel(log_level)
if os.getenv("HATCH_SPHINX_LOG_LEVEL", None):
    logging.basicConfig(level=log_level)


class SphinxBuildHook(BuildHookInterface[BuilderConfig]):
    """Build hook to run Sphinx tools during the build"""

    PLUGIN_NAME = "sphinx"

    def clean(
        self,
        versions: list[str],
    ) -> None:
        """Clean the output from all configured tools"""
        root_path = Path(self.root)
        all_tools = load_tools(self.config)

        for tool in all_tools:
            log.debug("Tool config: %s", asdict(tool))
            doc_path = tool.auto_doc_path(root_path)
            out_path = doc_path / tool.out_dir

            self.app.display(f"Cleaning {out_path}")
            shutil.rmtree(out_path, ignore_errors=True)

    def initialize(
        self,
        version: str,  # noqa: ARG002
        build_data: dict[str, Any],
    ) -> None:
        """Run whatever sphinx tools are configured"""

        # Start with some info for the process
        self.app.display_mini_header(self.PLUGIN_NAME)
        self.app.display_debug("options")
        self.app.display_debug(str(self.config), level=1)

        root_path = Path(self.root)
        all_tools = load_tools(self.config)

        for tool in all_tools:
            log.debug("Tool config: %s", asdict(tool))

            # Ensure output location exists
            doc_path = tool.auto_doc_path(root_path)
            out_path = doc_path / tool.out_dir
            out_path.mkdir(parents=True, exist_ok=True)

            # Locate the appropriate function to run for this tool
            try:
                tool_runner = getattr(self, f"_run_{tool.tool}")
            except AttributeError as e:
                self.app.display_error(
                    f"hatch-sphinx: unknown tool requested in: {tool.tool}"
                )
                self.app.display_error(f"hatch-sphinx: error: {e}")
                self.app.abort("hatch-sphinx: aborting build due to misconfiguration")
                raise

            # Run the tool
            self.app.display_info(f"hatch-sphinx: running sphinx tool {tool.tool}")
            result = tool_runner(doc_path, out_path, tool)

            # Report the result
            if result:
                self.app.display_success(
                    f"hatch-sphinx: tool {tool.tool} completed successfully"
                )
            else:
                self.app.display_error(f"hatch-sphinx: tool {tool.tool} failed")
                self.app.abort("hatch-sphinx: aborting on failure")

    def _run_build(self, doc_path: Path, out_path: Path, tool: ToolConfig) -> bool:
        """run sphinx-build"""
        args: list[str | None] = [
            *(
                tool.tool_build
                if tool.tool_build
                else [sys.executable, "-m", "sphinx", "build"]
            ),
            "-W" if tool.warnings else None,
            "--keep-going" if tool.keep_going else None,
            "-b" if tool.format else None,
            tool.format,
            *(shlex.split(tool.sphinx_opts) if tool.sphinx_opts else []),
            tool.source,
            str(out_path.resolve()),
        ]
        cleaned_args = list(filter(None, args))

        self.app.display_info(f"hatch-sphinx: executing: {cleaned_args}")

        try:
            res = subprocess.run(
                cleaned_args,
                check=False,
                cwd=doc_path,
                shell=False,
                env=self._env(tool),
            )
        except OSError as e:
            self.app.display_error(
                "hatch-sphinx: could not execute sphinx-build. Is it installed?"
            )
            self.app.display_error(f"hatch-sphinx: error: {e}")
            return False
        return res.returncode == 0

    def _run_apidoc(self, doc_path: Path, out_path: Path, tool: ToolConfig) -> bool:
        """run sphinx-apidoc"""
        args: list[str | None] = [
            *(
                tool.tool_apidoc
                if tool.tool_apidoc
                else [sys.executable, "-m", "sphinx.ext.apidoc"]
            ),
            "-o",
            str(out_path.resolve()),
            "-d",
            str(tool.depth),
            "--private" if tool.private else None,
            "--separate" if tool.separate else None,
            "-H" if tool.header else None,
            tool.header,
            *(shlex.split(tool.sphinx_opts) if tool.sphinx_opts else []),
            tool.source,
        ]
        cleaned_args = list(filter(None, args))

        self.app.display_info(f"hatch-sphinx: executing: {cleaned_args}")

        try:
            res = subprocess.run(
                cleaned_args,
                check=False,
                cwd=doc_path,
                shell=False,
                env=self._env(tool),
            )
        except OSError as e:
            self.app.display_error(
                "hatch-sphinx: could not execute sphinx-apidoc. Is it installed?"
            )
            self.app.display_error(f"hatch-sphinx: error: {e}")
            return False

        return res.returncode == 0

    def _run_custom(
        self,
        doc_path: Path,
        out_path: Path,  # pylint: disable=unused-argument
        tool: ToolConfig,
    ) -> bool:
        """run a custom command"""
        for c in tool.commands:
            shell = True if tool.shell is None else tool.shell
            if isinstance(c, str):
                c = c.replace("{python}", sys.executable)
            elif isinstance(c, (list, tuple)):
                c = [a if a != "{python}" else sys.executable for a in c]
                if shell:
                    self.app.display_warning(f"hatch-sphinx: converting command to single string in shell=true mode")
                    c = " ".join(c)

            self.app.display_info(f"hatch-sphinx: executing '{c}'")
            try:
                subprocess.run(
                    c, check=True, cwd=doc_path, shell=shell, env=self._env(tool)
                )
            except (OSError, subprocess.CalledProcessError) as e:
                self.app.display_error(f"hatch-sphinx: command failed: {e}")
                return False

        return True

    def _env(self, tool: ToolConfig) -> dict[str, str]:
        """merge in any extra environment variables specified in the config"""
        env = os.environ.copy()
        if tool.environment:
            env.update(tool.environment)
        return env


def load_tools(config: dict[str, Any]) -> Sequence[ToolConfig]:
    """Obtain all config related to this plugin"""
    tool_defaults = dataclass_defaults(ToolConfig)
    tool_defaults.update({k: config[k] for k in tool_defaults if k in config})
    return [
        ToolConfig(**{**tool_defaults, **tool_config})
        for tool_config in config.get("tools", [])
    ]


@dataclass
class ToolConfig(BuilderConfig):
    """A configuration for a sphinx tool."""

    # pylint: disable=too-many-instance-attributes

    tool: str
    """The sphinx tool to be used: apidoc, build, custom"""

    doc_dir: Optional[str] = None
    """Path where sphinx sources are to be found. defaults to doc, docs, .;
    relative to root of build"""

    out_dir: str = "output"
    """Path where sphinx build output will be saved. Relative to {doc_dir} """

    sphinx_opts: str = ""
    """Additional options for the tool; will be split using shlex"""

    environment: dict[str, str] = field(default_factory=dict)
    """Extra environment variables for tool execution"""

    # Config items for the 'build' tool

    tool_build: Optional[list[str]] = None
    """Command to use (defaults to `python -m sphinx build`)"""

    format: str = "html"
    """Output format selected for 'build' tool"""

    warnings: bool = False
    """-W: Turn warnings into errors"""

    keep_going: bool = False
    """--keep-going: With -W option, keep going after warnings"""

    # Config items for the 'apidoc' tool

    tool_apidoc: Optional[list[str]] = None
    """Command to use (defaults to `python -m sphinx apidoc`)"""

    depth: int = 3
    """Depth to recurse into the structures for API docs"""

    private: bool = False
    """Include private members in API docs"""

    separate: bool = True
    """Split each module into a separate page"""

    header: Optional[str] = None
    """Header to use on the API docs"""

    source: str = "."
    """Source to be included in the API docs"""

    # Config items for the 'commands' tool

    commands: list[str | list[str]] = field(default_factory=list)
    """Custom command to run within the {doc_dir}"""

    shell: Optional[bool] = None
    """Let the shell expand the command"""

    def auto_doc_path(self, root: Path) -> Path:
        """Determine the doc root for sphinx"""
        if self.doc_dir:
            return root / self.doc_dir
        for d in ["doc", "docs"]:
            p = root / d
            if p.exists() and p.is_dir():
                return p
        return root


def dataclass_defaults(obj: Any) -> dict[str, Any]:
    """Find the default values from the dataclass

    Permits easy updating from toml later
    """
    defaults: dict[str, Any] = {}
    for f in fields(obj):
        if f.default is not MISSING:
            defaults[f.name] = f.default
        elif f.default_factory is not MISSING:
            defaults[f.name] = f.default_factory()
    return defaults
