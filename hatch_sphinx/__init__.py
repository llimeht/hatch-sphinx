"""hatch-sphinx: hatchling build plugin for Sphinx document builder"""

try:
    from ._version import __version__  # type: ignore
except ImportError:
    __version__ = "0.0.0.dev"
