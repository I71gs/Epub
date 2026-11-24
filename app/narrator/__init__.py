"""Narrator domain package."""

from app.narrator.models import NarratorProfile
from app.narrator.registry import NarratorRegistry

__all__ = ["NarratorProfile", "NarratorRegistry"]
