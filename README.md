# Hatch Sphinx Plugin

A plugin for [Hatch](https://github.com/pypa/hatch) that allows you to build
documentation with Sphinx and include the output in your package distributions.


## Installation

`hatch-sphinx` is a plugin for the `hatchling` build system, so to use it
in your project you'll need to to be using that build-backend. You can add
`hatch-sphinx` to your project's `pyproject.toml` file as a `build-system`
requirement:

```toml
[build-system]
requires = ["hatchling", "hatch-sphinx"]
build-backend = "hatchling.build"
```

Standard Python package builders (`pip install <package>`, `python -m build`,
`hatchling build`, ...) will install the `hatch-sphinx` package for you
into the build environment.
(Or at least, they will do so once `hatch-sphinx` is uploaded to PyPI!)


## Usage

The set of Sphinx build steps needed by your project are configured in
the the `[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]` tables in
your `pyproject.toml` file. You can repeat this table multiple times to
run different tools (e.g. sphinx-apidoc and then sphinx-build).

Which tool is being run is configured via the `tool` configuration key.
The known values are `build`, `apidoc`, `custom`, and the different
configuration keys they support are listed below

### Common options

| Key | Default | Description |
| --- | ------- | ----------- |
| `tool` | required | Select the tool to be run `build`, `apidoc` or `custom` |
| `doc_dir` | `"doc"`, `"docs"`, `"."` (first existing) | The 'base' of the Sphinx documentation tree; set as the working directory prior to invoking any tool. |
| `out_dir` | `"output"` | The directory the tool outputs will be placed into, relative do `doc_dir`; created if it doesn't exist and deleted on clean. |
| `work_dir` | `"."` | The directory to run the commands in. All artifact patterns are relative to this directory. |
| `sphinx_opts` | `""` | Any additional options to be sent to the tool. |
| `environment` | `{}` | Dictionary of environment settings passed to the tool. |

### Tool `apidoc` options

| Key | Default | Description |
| --- | ------- | ----------- |
| `tool` | required | `apidoc` |
| `depth` | `3` | API depth to be included (`-d 3` option). |
| `private` | `false` | Include private members in documentation (`--private` option). |
| `separate` | `true` | Make a separate rst file per module (`--separate` option). |
| `header` | `None` | Header for documentation (`-H header` option). |
| `source` | `"."` | Source code to be included in the API docs. |
| `tool_apidoc` | `["python", "-m", "sphinx.ext.apidoc"` | Command to run as a list of strings |

### Tool `build` options

| Key | Default | Description |
| --- | ------- | ----------- |
| `tool` | required | `build` |
| `format` | `"html"` | Output format for documentation (`-b html` option). |
| `warnings` | `false` | Treat warnings as errors (`--warnings` option). |
| `keep_going` | `false` | Continue after warnings rather exiting immediately (`--keep-going` option). |
| `source` | `"."` | Source code to be included in the docs. |
| `tool_build` | `["python", "-m", "sphinx", "build"` | Command to run as a list of strings |

### Tool `custom` options

| Key | Default | Description |
| --- | ------- | ----------- |
| `tool` | required | `custom` |
| `commands` | required | List of commands to be executed; the magic string `{python}` is replaced with current interpreter (`sys.executable`). Each command can be a list of strings (preferred) or a single string. |
| `shell` | `false` | Whether to run the command via the shell (i.e. the `shell` parameter for `subprocess.run`) which permits wildcard expansion and scripting; note that the command cannot be a list of strings in `shell=true` mode. The standard warnings from `subprocess.run` to avoid using the shell apply here too. |
| `expand_globs` | `false` | Whether to expand globs in the command arguments. |

Notes:

 - Not all combinations of `shell=true`, `expand_globs=true` and the
  individual command being a single string are supported. The recommended
  configuration is to use `shell=false` and each command as a list, with
  `expand_globs=true` if wildcard expansion is needed.
 - Quoting within a single string is almost impossible to do in a portable
  fashion. If you need to work with filenames with spaces, for instance,
  then avoid trying to stack backslashes in this in an effort to get
  this to work.


### Examples

A sample configuration for generating the API docs and then running Sphinx

```toml
[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "apidoc"
source = "../src/mymodule"
out_dir = "source/api"
depth = 4
header = "MyModule API Documentation"

[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "build"
format = "html"
source = "source"
out_dir = "build"

[[tool.hatch.build.targets.wheel.hooks.sphinx.tools]]
tool = "custom"
out_dir = "build"
shell = false
expand_globs = true
commands = [
  [ "ls", "-l", "*.py" ],
  "ls -l *.py",
  [ "{python}", "-c", "import shutil; shutil.copytree('foo', 'bar')"],
]
```

## Notes

 - The examples above are focusing on the `wheel` stage but it is possible
   to build the docs in the `sdist` stage instead if desired.
 - The `output` directory is deleted in the clean step if used
   (e.g. `hatchling build --clean`)


## To-do list

 - support a `make` tool for `Makefile` based invocation of Sphinx
 - add option to allow `commands` to exit uncleanly


