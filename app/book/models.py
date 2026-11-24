"""Core data models for books and their chapters."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BookMetadata(BaseModel):
    """Optional descriptive metadata associated with a book."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    author: str | None = None
    language: str | None = None
    publisher: str | None = None
    identifier: str | None = None
    description: str | None = None


class Chapter(BaseModel):
    """A chapter-sized unit of book text."""

    id: str
    title: str
    index: int = Field(ge=0)
    text: str

    @field_validator("id", "title", "text")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class Book(BaseModel):
    """A source book and its ordered chapters."""

    id: str
    source_path: Path
    title: str
    author: str
    chapters: list[Chapter] = Field(default_factory=list)
    metadata: BookMetadata = Field(default_factory=BookMetadata)

    @field_validator("id", "title", "author")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("source_path")
    @classmethod
    def require_source_path(cls, value: Path) -> Path:
        if not str(value).strip():
            raise ValueError("must not be empty")
        return value


class ChapterProfile(BaseModel):
    """Structured analysis profile of a chapter."""

    chapter_id: str
    title: str
    summary: str
    tone: str
    importance: float = Field(ge=0.0, le=1.0)

    @field_validator("chapter_id", "title", "summary", "tone")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class BookProfile(BaseModel):
    """Structured analysis profile of a book."""

    title: str
    author: str
    genre: str
    overall_tone: str
    summary: str
    chapter_ids: list[str]

    @field_validator("title", "author", "genre", "overall_tone", "summary")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class SceneProfile(BaseModel):
    """Structured analysis profile of a scene within a chapter."""

    scene_id: str
    chapter_id: str
    start_text: str
    end_text: str
    summary: str
    scene_type: Literal["narration", "dialogue", "action", "description", "transition", "other"]

    @field_validator("scene_id", "chapter_id", "start_text", "end_text", "summary")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class CharacterProfile(BaseModel):
    """Profile of a character detected in a scene."""

    name: str
    description: str

    @field_validator("name", "description")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class DialogueSegment(BaseModel):
    """A segment of dialogue containing spoken text and speaker attribution."""

    speaker: str | None = None
    spoken_text: str
    surrounding_narration: str | None = None

    @field_validator("spoken_text")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("speaker", "surrounding_narration")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value if value else None


class NarrationSegment(BaseModel):
    """Segment of narration or dialogue with speech parameters."""

    text: str
    voice_role: str
    emotion: str
    intensity: float = Field(ge=0.0, le=1.0)
    speaking_rate: float = Field(ge=0.5, le=2.0)
    pause_before: float = Field(ge=0.0, le=10.0)
    pause_after: float = Field(ge=0.0, le=10.0)
    emphasis: str

    @field_validator("text", "voice_role", "emotion", "emphasis")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class NarrationPlan(BaseModel):
    """Narration plan for a scene containing sequential speech segments."""

    scene_id: str
    segments: list[NarrationSegment]

    @field_validator("scene_id")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


__all__ = [
    "Book",
    "Chapter",
    "BookMetadata",
    "BookProfile",
    "ChapterProfile",
    "SceneProfile",
    "CharacterProfile",
    "DialogueSegment",
    "NarrationSegment",
    "NarrationPlan",
]