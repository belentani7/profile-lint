"""Deterministic, dependency-free checks for a GitHub profile README."""

from .rules import Finding, lint

__all__ = ["Finding", "lint"]
__version__ = "0.1.0"
