"""Narrator profile data model."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator


class NarratorProfile(BaseModel):
    """Metadata for one narrator and its reference audio file."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    language: str = "eng"
    description: str | None = None
    reference_path: Path | None = None

    @field_validator("id", "name", "language")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value