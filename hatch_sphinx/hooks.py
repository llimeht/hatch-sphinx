"""Register hooks for the plugin."""

from hatchling.plugin import hookimpl

from hatch_sphinx.plugin import SphinxBuildHook


@hookimpl
def hatch_register_build_hook() -> type[SphinxBuildHook]:
    """Get the hook implementation."""
    return SphinxBuildHook
