"""Comprobaciones deterministas y sin dependencias para README de perfiles de GitHub."""

from .rules import Finding, lint, summarize

__all__ = ["Finding", "lint", "summarize"]
__version__ = "0.2.0"
