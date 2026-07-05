"""Sphinx configuration for the alchemiq documentation site."""

project = "alchemiq"
author = "Trifonov Nikita"
copyright = "2026, Trifonov Nikita"
version = release = "0.1.0"  # matches pyproject project.version

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinx_copybutton",
]
# Deliberately NOT enabled: sphinx.ext.napoleon (docstrings are native reST, not
# Google/Numpy) and sphinx.ext.doctest (examples are illustrative/async, not executable).

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

html_theme = "furo"
html_title = "alchemiq"

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}
intersphinx_timeout = 10

myst_enable_extensions = ["colon_fence", "deflist"]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
