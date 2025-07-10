"""hatch-sphinx: hatchling build plugin for Sphinx document system"""

from __future__ import annotations

from collections.abc import Sequence
import contextlib
from dataclasses import MISSING, asdict, dataclass, field, fields
import logging
import glob
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
from typing import Any, Optional

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.config import BuilderConfig


try:
    from contextlib import chdir

except ImportError:
    # CRUFT: contextlib.chdir added Python 3.11

    class chdir(contextlib.AbstractContextManager):  # type: ignore  # pylint: disable=invalid-name
        """Non thread-safe context manager to change the current working directory."""

        def __init__(self, path: str) -> None:
            self.path = path
            self._old_cwd: list[str] = []

        def __enter__(self) -> None:
            self._old_cwd.append(os.getcwd())
            os.chdir(self.path)

        def __exit__(self, *excinfo: Any) -> None:
            os.chdir(self._old_cwd.pop())


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
        tool.source = tool.source.rstrip("/")

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
            *(tool.source + os.sep + e for e in tool.exclude),
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

            # Matrix of options
            #
            #   shell   globs   type(c)   supported
            #
            #   True    True     str         ✘
            #   True    True     list        ✘
            #   True    False    str         ✔
            #   True    False    list        ✘
            #
            #   False   True     str         ✔
            #   False   True     list        ✔
            #   False   False    str         ✔
            #   False   False    list        ✔

            # When args is a list, args needs to be joined to make a string
            # for the shell in shell=True mode, but this cannot be done
            # reliably, so is unsupported

            aborting = False
            if not isinstance(c, (str, list, tuple)):
                # shouldn't be possible but better to check than have an issue
                self.app.display_error(
                    f"hatch-sphinx: unknown type for command {type(c)}"
                )
                aborting = True

            # normalise the iterable type
            if isinstance(c, tuple):
                c = list(c)

            if tool.shell and not isinstance(c, str):
                self.app.display_error(
                    "hatch-sphinx: cannot pass a list of args for a custom command "
                    "in shell=true mode."
                )
                aborting = True

            if tool.expand_globs and tool.shell:
                self.app.display_error(
                    "hatch-sphinx: expanding globs cannot be done reliably in shell=true mode."
                )
                aborting = True

            if aborting:
                self.app.abort("hatch-sphinx: exiting on misconfiguration.")

            # Where we can, work with a list not a str
            if not tool.shell and not isinstance(c, list):
                c = shlex.split(c)
                self.app.display_debug(
                    "hatch-sphinx: splitting the command with shlex.split; avoid "
                    "this by specifying the command as a list in the configuration. "
                    f"Command: {c}"
                )

            # c is either a list: [command, option1, option2, ...]
            #   or a str: "command option1 option2"
            # process it for:
            #   - tokens in the command like {python}, always
            #   - glob expansion, if configured

            c = self._replace_tokens(c)

            if tool.expand_globs:
                assert isinstance(c, list)  # config options above enforce this
                c = self._expand_globs(c, doc_path)

            self.app.display_info(f"hatch-sphinx: executing '{c}'")

            try:
                subprocess.run(
                    c, check=True, cwd=doc_path, shell=tool.shell, env=self._env(tool)
                )
            except (OSError, subprocess.CalledProcessError) as e:
                self.app.display_error(f"hatch-sphinx: command failed: {e}")
                return False

        return True

    def _env(self, tool: ToolConfig) -> dict[str, str]:
        """merge in any extra environment variables specified in the config"""
        env = os.environ.copy()
        if tool.environment:
            for k, v in tool.environment.items():
                if k in env:
                    if k == "PYTHONPATH":
                        env[k] = f"{v}{os.pathsep}{env[k]}"
                    else:
                        self.app.display_warning(
                            "hatch-sphinx: overwriting environment from configuration: "
                            f"{k}: {v}"
                        )
                else:
                    env[k] = v
        return env

    def _expand_globs(self, args: list[str], root_dir: str | Path) -> list[str]:
        """expand globs in the command"""
        expanded = []
        for a in args:
            if "*" in a or "?" in a or "[" in a:
                # CRUFT: root_dir arg added to glob in Python 3.10
                # globs = glob.glob(a, root_dir=root_dir)
                with chdir(root_dir):
                    globs = glob.glob(a)
                if not globs:
                    self.app.display_warning(
                        f"hatch-sphinx: glob '{a}' evaluated to empty string: "
                        "this is probably not what you want."
                    )
                expanded.extend(globs)
            else:
                expanded.append(a)
        return expanded

    def _replace_tokens(self, args: str | list[str]) -> str | list[str]:
        """replace defined tokens in the command"""
        if isinstance(args, str):
            return self._replace_tokens_str(args)

        return [self._replace_tokens_str(a) for a in args]

    def _replace_tokens_str(self, arg: str) -> str:
        """replace defined tokens in the command"""
        return arg.replace("{python}", sys.executable)


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

    exclude: list[str] = field(default_factory=list)
    """Patterns of filepaths to exclude from analysis"""

    # Config items for the 'commands' tool

    commands: list[str | list[str]] = field(default_factory=list)
    """Custom command to run within the {doc_dir}; if provided as a str then
    it is split with shlex.split prior to use"""

    shell: bool = False
    """Let the shell expand the command"""

    expand_globs: bool = False
    """Expand globs in the command prior to running, particularly useful for
    avoiding shell=true on non-un*x systems"""

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
