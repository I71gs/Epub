"""Book Intelligence analysis using language models and caching."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from app.book.models import Book, BookProfile, Chapter, ChapterProfile, SceneProfile, CharacterProfile, DialogueSegment, NarrationSegment, NarrationPlan
from app.core.config import load_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Exception raised when language model analysis fails."""

    pass


@runtime_checkable
class LLMAdapter(Protocol):
    """Interface for language model API communication."""

    def generate(self, prompt: str, system_instruction: str | None = None) -> str:
        """Send a prompt to the LLM and return its raw response string."""
        ...


class DefaultLLMAdapter:
    """Default adapter calling Gemini or OpenAI APIs headlessly using httpx."""

    def generate(self, prompt: str, system_instruction: str | None = None) -> str:
        """Call Gemini or OpenAI API based on configured environment variables."""
        gemini_key = os.getenv("GEMINI_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if gemini_key:
            return self._call_gemini(gemini_key, prompt, system_instruction)
        elif openai_key:
            return self._call_openai(openai_key, prompt, system_instruction)
        else:
            raise LLMError(
                "No LLM API key found in environment. Please set GEMINI_API_KEY or OPENAI_API_KEY."
            )

    def _call_gemini(
        self, api_key: str, prompt: str, system_instruction: str | None
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            res_data = response.json()
            return str(res_data["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as exc:
            logger.exception("Gemini API call failed")
            raise LLMError(f"Gemini API call failed: {exc}") from exc

    def _call_openai(
        self, api_key: str, prompt: str, system_instruction: str | None
    ) -> str:
        openai_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        url = f"{openai_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "response_format": {"type": "json_object"},
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            res_data = response.json()
            return str(res_data["choices"][0]["message"]["content"])
        except Exception as exc:
            logger.exception("OpenAI API call failed")
            raise LLMError(f"OpenAI API call failed: {exc}") from exc


class BookAnalyzer:
    """Analyze a book's structure and chapters using an LLM, with local caching and graceful fallback."""

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.llm_adapter = llm_adapter or DefaultLLMAdapter()
        settings = load_settings()
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_file = self.cache_dir / "analysis_cache.json"
        self.cache_enabled = cache_enabled

    def analyze(self, book: Book) -> tuple[BookProfile, list[ChapterProfile]]:
        """Analyze the book and its chapters, returning (BookProfile, list[ChapterProfile]).

        If cache is enabled and hit, loads results from disk. Otherwise calls the LLM.
        In case of LLM or validation errors, returns graceful fallback stub profiles.
        """
        if self.cache_enabled:
            try:
                cache = self._load_cache()
                book_hash = self._compute_book_hash(book)
                if book_hash in cache:
                    logger.info("Cache hit for book: %s (%s)", book.title, book.id)
                    entry = cache[book_hash]
                    book_profile = BookProfile.model_validate(entry["book_profile"])
                    chapter_profiles = [
                        ChapterProfile.model_validate(cp)
                        for cp in entry["chapter_profiles"]
                    ]
                    return book_profile, chapter_profiles
            except Exception as e:
                logger.warning("Failed to load or validate cache entry: %s. Re-running analysis.", e)

        try:
            book_profile, chapter_profiles = self._run_analysis(book)
            if self.cache_enabled:
                try:
                    book_hash = self._compute_book_hash(book)
                    self._save_to_cache(book_hash, book_profile, chapter_profiles)
                except Exception as e:
                    logger.warning("Failed to save analysis results to cache: %s", e)
            return book_profile, chapter_profiles
        except Exception as exc:
            logger.error(
                "Analysis failed for book %s (%s). Generating graceful fallback profiles. Error: %s",
                book.title,
                book.id,
                exc,
            )
            return self._generate_fallback(book)

    def _run_analysis(self, book: Book) -> tuple[BookProfile, list[ChapterProfile]]:
        if not book.chapters:
            raise ValueError("Book contains no chapters to analyze")

        chapter_profiles: list[ChapterProfile] = []
        for chapter in book.chapters:
            prompt = (
                f"Analyze the following chapter from the book '{book.title}' by {book.author}:\n\n"
                f"Chapter Title: {chapter.title}\n"
                f"Chapter Text:\n{chapter.text}\n\n"
                "Provide a JSON object with the following fields:\n"
                "- title: The title of the chapter (or a concise summary title if untitled)\n"
                "- summary: A concise, structured summary of the chapter events\n"
                "- tone: The prevailing tone of the chapter (e.g. suspenseful, lighthearted, melancholic)\n"
                "- importance: A float value between 0.0 and 1.0 representing how critical this chapter is to the overall plot/theme."
            )
            system_instruction = (
                "You are a literary analysis assistant. You must respond ONLY with a valid JSON object matching the requested schema. "
                "Do not wrap your response in markdown code blocks or add any other text."
            )
            try:
                response_text = self.llm_adapter.generate(
                    prompt, system_instruction=system_instruction
                )
                data = self._parse_json_response(response_text)
                # Inject chapter_id from source chapter to guarantee accuracy
                data["chapter_id"] = chapter.id
                cp = ChapterProfile.model_validate(data)
                chapter_profiles.append(cp)
            except Exception as e:
                raise LLMError(f"Failed to analyze chapter {chapter.id}: {e}") from e

        # Analyze the overall book using the chapter profiles
        chapter_summaries_text = "\n".join(
            f"- Chapter '{cp.title}' (ID: {cp.chapter_id}): {cp.summary}"
            for cp in chapter_profiles
        )
        prompt = (
            f"Analyze the overall book based on its details and chapter summaries:\n\n"
            f"Title: {book.title}\n"
            f"Author: {book.author}\n"
            f"Chapter Summaries:\n{chapter_summaries_text}\n\n"
            "Provide a JSON object with the following fields:\n"
            "- genre: The genre of the book\n"
            "- overall_tone: The overall tone of the book\n"
            "- summary: A comprehensive summary of the entire book."
        )
        system_instruction = (
            "You are a literary analysis assistant. You must respond ONLY with a valid JSON object matching the requested schema. "
            "Do not wrap your response in markdown code blocks or add any other text."
        )
        try:
            response_text = self.llm_adapter.generate(
                prompt, system_instruction=system_instruction
            )
            data = self._parse_json_response(response_text)
            # Inject book details
            data["title"] = book.title
            data["author"] = book.author
            data["chapter_ids"] = [c.id for c in book.chapters]
            book_profile = BookProfile.model_validate(data)
        except Exception as e:
            raise LLMError(f"Failed to analyze book overall metadata: {e}") from e

        return book_profile, chapter_profiles

    def _generate_fallback(
        self, book: Book
    ) -> tuple[BookProfile, list[ChapterProfile]]:
        chapter_profiles: list[ChapterProfile] = []
        for idx, chapter in enumerate(book.chapters):
            chapter_profiles.append(
                ChapterProfile(
                    chapter_id=chapter.id,
                    title=chapter.title or f"Chapter {idx + 1}",
                    summary="Analysis unavailable (LLM or validation failure).",
                    tone="unknown",
                    importance=0.5,
                )
            )
        book_profile = BookProfile(
            title=book.title,
            author=book.author,
            genre="unknown",
            overall_tone="unknown",
            summary="Analysis unavailable (LLM or validation failure).",
            chapter_ids=[c.id for c in book.chapters],
        )
        return book_profile, chapter_profiles

    def _compute_book_hash(self, book: Book) -> str:
        hasher = hashlib.sha256()
        hasher.update(book.id.encode("utf-8"))
        hasher.update(book.title.encode("utf-8"))
        hasher.update(book.author.encode("utf-8"))
        for chapter in book.chapters:
            hasher.update(chapter.id.encode("utf-8"))
            hasher.update(chapter.title.encode("utf-8"))
            hasher.update(chapter.text.encode("utf-8"))
        return hasher.hexdigest()

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_file.is_file():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Could not read analysis cache from %s: %s", self.cache_file, e)
            return {}

    def _save_to_cache(
        self,
        book_hash: str,
        book_profile: BookProfile,
        chapter_profiles: list[ChapterProfile],
    ) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache = self._load_cache()
        cache[book_hash] = {
            "book_profile": book_profile.model_dump(),
            "chapter_profiles": [cp.model_dump() for cp in chapter_profiles],
        }

        # Atomic replacement
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.cache_file.parent, prefix=".analysis_cache.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(cache, file, indent=2)
            os.replace(temporary_name, self.cache_file)
        except OSError:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("```"):
                    start_idx = i + 1
                    break
            end_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("```"):
                    end_idx = i
                    break
            text = "\n".join(lines[start_idx:end_idx]).strip()
        return json.loads(text)  # type: ignore[no-any-return]


class SceneAnalyzer:
    """Analyze a chapter's text to detect and segment scenes, with caching and fallback."""

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.llm_adapter = llm_adapter or DefaultLLMAdapter()
        settings = load_settings()
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_file = self.cache_dir / "scene_cache.json"
        self.cache_enabled = cache_enabled

    def analyze(self, chapter: Chapter) -> list[SceneProfile]:
        """Analyze the chapter text to detect scenes, returning a list of SceneProfiles.

        If cache is enabled and hit, loads results from disk. Otherwise calls the LLM.
        In case of LLM or validation errors, returns graceful fallback stub profiles.
        """
        if self.cache_enabled:
            try:
                cache = self._load_cache()
                chapter_hash = self._compute_chapter_hash(chapter)
                if chapter_hash in cache:
                    logger.info("Cache hit for chapter: %s (%s)", chapter.title, chapter.id)
                    entry = cache[chapter_hash]
                    return [SceneProfile.model_validate(sp) for sp in entry]
            except Exception as e:
                logger.warning("Failed to load or validate scene cache entry: %s. Re-running analysis.", e)

        try:
            scene_profiles = self._run_analysis(chapter)
            if self.cache_enabled:
                try:
                    chapter_hash = self._compute_chapter_hash(chapter)
                    self._save_to_cache(chapter_hash, scene_profiles)
                except Exception as e:
                    logger.warning("Failed to save scene analysis results to cache: %s", e)
            return scene_profiles
        except Exception as exc:
            logger.error(
                "Scene analysis failed for chapter %s (%s). Generating graceful fallback profiles. Error: %s",
                chapter.title,
                chapter.id,
                exc,
            )
            return self._generate_fallback(chapter)

    def _run_analysis(self, chapter: Chapter) -> list[SceneProfile]:
        if not chapter.text.strip():
            raise ValueError("Chapter text is empty")

        prompt = (
            f"Analyze the following chapter to detect and segment it into scenes:\n\n"
            f"Chapter ID: {chapter.id}\n"
            f"Chapter Title: {chapter.title}\n"
            f"Chapter Text:\n{chapter.text}\n\n"
            "Identify each scene and return a JSON object with a single key 'scenes' containing a list of scenes. "
            "Each scene object in the list must contain the following fields:\n"
            "- scene_id: A unique identifier for the scene (e.g. 'scene-1', 'scene-2')\n"
            "- start_text: The exact sentence or clause where the scene starts\n"
            "- end_text: The exact sentence or clause where the scene ends\n"
            "- summary: A brief summary of what happens in the scene\n"
            "- scene_type: Must be exactly one of: 'narration', 'dialogue', 'action', 'description', 'transition', 'other'"
        )
        system_instruction = (
            "You are a literary analysis assistant. You must respond ONLY with a valid JSON object matching the requested schema. "
            "Do not wrap your response in markdown code blocks or add any other text."
        )
        
        response_text = self.llm_adapter.generate(
            prompt, system_instruction=system_instruction
        )
        data = self._parse_json_response(response_text)
        scenes_data = data.get("scenes", [])
        if not isinstance(scenes_data, list):
            raise ValueError("Expected a list of scenes in 'scenes' key")

        scene_profiles = []
        for idx, scene_item in enumerate(scenes_data):
            # Inject chapter_id from source chapter to guarantee accuracy
            scene_item["chapter_id"] = chapter.id
            if not scene_item.get("scene_id"):
                scene_item["scene_id"] = f"{chapter.id}-scene-{idx + 1}"
            sp = SceneProfile.model_validate(scene_item)
            scene_profiles.append(sp)
            
        return scene_profiles

    def _generate_fallback(self, chapter: Chapter) -> list[SceneProfile]:
        start_txt = chapter.text[:100].strip() or "Chapter start"
        end_txt = chapter.text[-100:].strip() or "Chapter end"
        return [
            SceneProfile(
                scene_id=f"{chapter.id}-scene-fallback",
                chapter_id=chapter.id,
                start_text=start_txt,
                end_text=end_txt,
                summary="Analysis unavailable (LLM or validation failure).",
                scene_type="other",
            )
        ]

    def _compute_chapter_hash(self, chapter: Chapter) -> str:
        hasher = hashlib.sha256()
        hasher.update(chapter.id.encode("utf-8"))
        hasher.update(chapter.title.encode("utf-8"))
        hasher.update(chapter.text.encode("utf-8"))
        return hasher.hexdigest()

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_file.is_file():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Could not read scene cache from %s: %s", self.cache_file, e)
            return {}

    def _save_to_cache(
        self,
        chapter_hash: str,
        scene_profiles: list[SceneProfile],
    ) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache = self._load_cache()
        cache[chapter_hash] = [sp.model_dump() for sp in scene_profiles]

        # Atomic replacement
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.cache_file.parent, prefix=".scene_cache.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(cache, file, indent=2)
            os.replace(temporary_name, self.cache_file)
        except OSError:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("```"):
                    start_idx = i + 1
                    break
            end_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("```"):
                    end_idx = i
                    break
            text = "\n".join(lines[start_idx:end_idx]).strip()
        return json.loads(text)  # type: ignore[no-any-return]


class CharacterDialogueAnalyzer:
    """Analyze a scene's text to detect characters and dialogue segments, with caching and fallback."""

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.llm_adapter = llm_adapter or DefaultLLMAdapter()
        settings = load_settings()
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_file = self.cache_dir / "character_dialogue_cache.json"
        self.cache_enabled = cache_enabled

    def analyze(
        self, scene: SceneProfile, scene_text: str
    ) -> tuple[list[CharacterProfile], list[DialogueSegment]]:
        """Analyze scene text to detect characters and dialogue segments.

        If cache is enabled and hit, loads results from disk. Otherwise calls the LLM.
        In case of LLM or validation errors, returns graceful fallback stub profiles.
        """
        if self.cache_enabled:
            try:
                cache = self._load_cache()
                scene_hash = self._compute_scene_hash(scene, scene_text)
                if scene_hash in cache:
                    logger.info("Cache hit for scene: %s", scene.scene_id)
                    entry = cache[scene_hash]
                    characters = [CharacterProfile.model_validate(c) for c in entry["characters"]]
                    dialogue_segments = [DialogueSegment.model_validate(d) for d in entry["dialogue_segments"]]
                    return characters, dialogue_segments
            except Exception as e:
                logger.warning("Failed to load or validate character dialogue cache entry: %s. Re-running analysis.", e)

        try:
            characters, dialogue_segments = self._run_analysis(scene, scene_text)
            if self.cache_enabled:
                try:
                    scene_hash = self._compute_scene_hash(scene, scene_text)
                    self._save_to_cache(scene_hash, characters, dialogue_segments)
                except Exception as e:
                    logger.warning("Failed to save character dialogue analysis results to cache: %s", e)
            return characters, dialogue_segments
        except Exception as exc:
            logger.error(
                "Character & dialogue analysis failed for scene %s. Generating graceful fallback profiles. Error: %s",
                scene.scene_id,
                exc,
            )
            return self._generate_fallback(scene, scene_text)

    def _run_analysis(
        self, scene: SceneProfile, scene_text: str
    ) -> tuple[list[CharacterProfile], list[DialogueSegment]]:
        if not scene_text.strip():
            raise ValueError("Scene text is empty")

        prompt = (
            f"Analyze the following scene text to detect characters and dialogue segments:\n\n"
            f"Scene ID: {scene.scene_id}\n"
            f"Scene Summary: {scene.summary}\n"
            f"Scene Text:\n{scene_text}\n\n"
            "Identify all characters appearing or mentioned in the scene, and extract all dialogue segments. "
            "Return a JSON object with exactly two keys: 'characters' and 'dialogue_segments'.\n"
            "Each character object in the 'characters' list must contain:\n"
            "- name: The name of the character\n"
            "- description: A brief description or role of the character in this scene\n\n"
            "Each dialogue segment object in the 'dialogue_segments' list must contain:\n"
            "- speaker: The name of the character speaking, or null if the speaker is unknown or not identifiable\n"
            "- spoken_text: The exact text spoken by the character\n"
            "- surrounding_narration: Any narration surrounding the spoken text (e.g. 'she said', 'he whispered'), or null if none exists"
        )
        system_instruction = (
            "You are a literary analysis assistant. You must respond ONLY with a valid JSON object matching the requested schema. "
            "Do not wrap your response in markdown code blocks or add any other text."
        )

        response_text = self.llm_adapter.generate(
            prompt, system_instruction=system_instruction
        )
        data = self._parse_json_response(response_text)
        
        characters_data = data.get("characters", [])
        dialogue_data = data.get("dialogue_segments", [])
        if not isinstance(characters_data, list) or not isinstance(dialogue_data, list):
            raise ValueError("Expected list for 'characters' and 'dialogue_segments' keys")

        characters = [CharacterProfile.model_validate(c) for c in characters_data]
        dialogue_segments = [DialogueSegment.model_validate(d) for d in dialogue_data]
        return characters, dialogue_segments

    def _generate_fallback(
        self, scene: SceneProfile, scene_text: str
    ) -> tuple[list[CharacterProfile], list[DialogueSegment]]:
        # Graceful fallback: return empty list of characters and one dialogue segment representing the fallback
        return (
            [],
            [
                DialogueSegment(
                    speaker=None,
                    spoken_text=scene_text[:100].strip() or "Fallback spoken text",
                    surrounding_narration="Analysis unavailable (LLM or validation failure).",
                )
            ],
        )

    def _compute_scene_hash(self, scene: SceneProfile, scene_text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(scene.scene_id.encode("utf-8"))
        hasher.update(scene.chapter_id.encode("utf-8"))
        hasher.update(scene.scene_type.encode("utf-8"))
        hasher.update(scene_text.encode("utf-8"))
        return hasher.hexdigest()

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_file.is_file():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Could not read character dialogue cache from %s: %s", self.cache_file, e)
            return {}

    def _save_to_cache(
        self,
        scene_hash: str,
        characters: list[CharacterProfile],
        dialogue_segments: list[DialogueSegment],
    ) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache = self._load_cache()
        cache[scene_hash] = {
            "characters": [c.model_dump() for c in characters],
            "dialogue_segments": [d.model_dump() for d in dialogue_segments],
        }

        # Atomic replacement
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.cache_file.parent, prefix=".character_dialogue_cache.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(cache, file, indent=2)
            os.replace(temporary_name, self.cache_file)
        except OSError:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("```"):
                    start_idx = i + 1
                    break
            end_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("```"):
                    end_idx = i
                    break
            text = "\n".join(lines[start_idx:end_idx]).strip()
        return json.loads(text)  # type: ignore[no-any-return]


class NarrationPlanner:
    """Planners speech details and parameters for narrating scenes, with caching and fallback."""

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.llm_adapter = llm_adapter or DefaultLLMAdapter()
        settings = load_settings()
        self.cache_dir = cache_dir or settings.data_dir
        self.cache_file = self.cache_dir / "narration_plan_cache.json"
        self.cache_enabled = cache_enabled

    def plan(
        self,
        scene: SceneProfile,
        scene_text: str,
        characters: list[CharacterProfile],
        dialogue_segments: list[DialogueSegment],
    ) -> NarrationPlan:
        """Plan narration speech details for scene text.

        If cache is enabled and hit, loads results from disk. Otherwise calls the LLM.
        In case of LLM or validation errors, returns graceful fallback stub plan.
        """
        if self.cache_enabled:
            try:
                cache = self._load_cache()
                scene_hash = self._compute_scene_hash(scene, scene_text)
                if scene_hash in cache:
                    logger.info("Cache hit for narration plan of scene: %s", scene.scene_id)
                    entry = cache[scene_hash]
                    return NarrationPlan.model_validate(entry)
            except Exception as e:
                logger.warning("Failed to load or validate narration plan cache entry: %s. Re-running plan.", e)

        try:
            narration_plan = self._run_analysis(scene, scene_text, characters, dialogue_segments)
            if self.cache_enabled:
                try:
                    scene_hash = self._compute_scene_hash(scene, scene_text)
                    self._save_to_cache(scene_hash, narration_plan)
                except Exception as e:
                    logger.warning("Failed to save narration plan results to cache: %s", e)
            return narration_plan
        except Exception as exc:
            logger.error(
                "Narration planning failed for scene %s. Generating graceful fallback plan. Error: %s",
                scene.scene_id,
                exc,
            )
            return self._generate_fallback(scene, scene_text)

    def _run_analysis(
        self,
        scene: SceneProfile,
        scene_text: str,
        characters: list[CharacterProfile],
        dialogue_segments: list[DialogueSegment],
    ) -> NarrationPlan:
        if not scene_text.strip():
            raise ValueError("Scene text is empty")

        prompt = (
            f"Analyze the following scene text, characters, and dialogue segments to produce a Narration Plan.\n\n"
            f"Scene ID: {scene.scene_id}\n"
            f"Scene Summary: {scene.summary}\n"
            f"Scene Text:\n{scene_text}\n\n"
            f"Characters in Scene:\n" + "\n".join(f"- {c.name}: {c.description}" for c in characters) + "\n\n"
            f"Dialogue Segments:\n" + "\n".join(f"- {d.speaker or 'Unknown'}: '{d.spoken_text}' (Narration: {d.surrounding_narration or 'None'})" for d in dialogue_segments) + "\n\n"
            "Produce a sequential list of speech segments that cover the entire scene text word-for-word without modifying, rewriting, or omitting any part of the original scene text.\n"
            "Return a JSON object with exactly one key 'segments' containing the list of segments. Each segment must have the following fields:\n"
            "- text: The exact substring of the scene text corresponding to this narration/dialogue part (must match the original text word-for-word)\n"
            "- voice_role: Either 'narrator' or the exact name of the character speaking\n"
            "- emotion: The emotion to be used (e.g. 'neutral', 'happy', 'sad', 'whispering', 'angry', etc.)\n"
            "- intensity: A float value between 0.0 and 1.0 representing the emotional intensity\n"
            "- speaking_rate: A speed factor float value between 0.5 and 2.0 (1.0 is normal)\n"
            "- pause_before: A pause duration in seconds (float >= 0.0)\n"
            "- pause_after: A pause duration in seconds (float >= 0.0)\n"
            "- emphasis: The emphasis level (e.g. 'none', 'strong', 'moderate')"
        )
        system_instruction = (
            "You are a narrative planner. You must respond ONLY with a valid JSON object matching the requested schema. "
            "Never rewrite or modify the source text in the 'text' field. "
            "Do not wrap your response in markdown code blocks or add any other text."
        )

        response_text = self.llm_adapter.generate(
            prompt, system_instruction=system_instruction
        )
        data = self._parse_json_response(response_text)
        
        segments_data = data.get("segments", [])
        if not isinstance(segments_data, list):
            raise ValueError("Expected list for 'segments' key")

        segments = [NarrationSegment.model_validate(seg) for seg in segments_data]
        return NarrationPlan(scene_id=scene.scene_id, segments=segments)

    def _generate_fallback(self, scene: SceneProfile, scene_text: str) -> NarrationPlan:
        return NarrationPlan(
            scene_id=scene.scene_id,
            segments=[
                NarrationSegment(
                    text=scene_text.strip() or "Fallback scene text",
                    voice_role="narrator",
                    emotion="neutral",
                    intensity=0.5,
                    speaking_rate=1.0,
                    pause_before=0.0,
                    pause_after=0.0,
                    emphasis="none",
                )
            ],
        )

    def _compute_scene_hash(self, scene: SceneProfile, scene_text: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(scene.scene_id.encode("utf-8"))
        hasher.update(scene.chapter_id.encode("utf-8"))
        hasher.update(scene.scene_type.encode("utf-8"))
        hasher.update(scene_text.encode("utf-8"))
        return hasher.hexdigest()

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_file.is_file():
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Could not read narration plan cache from %s: %s", self.cache_file, e)
            return {}

    def _save_to_cache(self, scene_hash: str, plan: NarrationPlan) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache = self._load_cache()
        cache[scene_hash] = plan.model_dump()

        # Atomic replacement
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.cache_file.parent, prefix=".narration_plan_cache.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(cache, file, indent=2)
            os.replace(temporary_name, self.cache_file)
        except OSError:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("```"):
                    start_idx = i + 1
                    break
            end_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].startswith("```"):
                    end_idx = i
                    break
            text = "\n".join(lines[start_idx:end_idx]).strip()
        return json.loads(text)  # type: ignore[no-any-return]


__all__ = ["LLMError", "LLMAdapter", "DefaultLLMAdapter", "BookAnalyzer", "SceneAnalyzer", "CharacterDialogueAnalyzer", "NarrationPlanner"]
