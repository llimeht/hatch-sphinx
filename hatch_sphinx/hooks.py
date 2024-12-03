"""Register hooks for the plugin."""

from hatchling.plugin import hookimpl
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.config import BuilderConfig

from hatch_sphinx.plugin import SphinxBuildHook


@hookimpl
def hatch_register_build_hook() -> type[BuildHookInterface[BuilderConfig]]:
    """Get the hook implementation."""
    return SphinxBuildHook
