# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import importlib.metadata

# -- Project information -----------------------------------------------------

project = "schlepper"
author = "William Woodruff"
copyright = f"2026, {author}"
release = importlib.metadata.version("schlepper")
version = release

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_member_order = "bysource"
autodoc_typehints = "both"
autodoc_class_signature = "mixed"

autoclass_content = "class"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path: list[str] = []
exclude_patterns: list[str] = ["_build"]

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = "schlepper"
