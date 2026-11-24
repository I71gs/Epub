import unittest
import json
import tempfile
import shutil
from pathlib import Path
from pydantic import ValidationError

from app.book.models import Book, Chapter, BookProfile, ChapterProfile
from app.book.intelligence import BookAnalyzer, LLMError, LLMAdapter


class MockLLMAdapter:
    """Mock LLM adapter to simulate LLM api responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.responses: list[str] = []
        self.exception: Exception | None = None

    def add_response(self, text: str) -> None:
        self.responses.append(text)

    def generate(self, prompt: str, system_instruction: str | None = None) -> str:
        self.calls.append((prompt, system_instruction))
        if self.exception:
            raise self.exception
        if not self.responses:
            raise RuntimeError("No mock response configured")
        return self.responses.pop(0)


class BookIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp_dir)
        self.mock_adapter = MockLLMAdapter()
        self.analyzer = BookAnalyzer(
            llm_adapter=self.mock_adapter,
            cache_dir=self.cache_dir,
            cache_enabled=True,
        )

        # Create a sample book
        self.chapter1 = Chapter(id="c1", title="Beginning", index=0, text="The story begins in a dark forest.")
        self.chapter2 = Chapter(id="c2", title="Middle", index=1, text="They meet an old wizard who offers a map.")
        self.book = Book(
            id="book-123",
            source_path=Path("sample.epub"),
            title="The Map of Wandering",
            author="J. R. Wandering",
            chapters=[self.chapter1, self.chapter2],
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir)

    def test_analyzer_success_flow(self) -> None:
        # Mock responses for 2 chapters and overall book
        self.mock_adapter.add_response(
            '{"title": "Beginning", "summary": "The hero enters the forest.", "tone": "dark", "importance": 0.6}'
        )
        self.mock_adapter.add_response(
            '{"title": "The Wizard\'s Offer", "summary": "The wizard gives a map.", "tone": "mysterious", "importance": 0.8}'
        )
        self.mock_adapter.add_response(
            '{"genre": "Fantasy", "overall_tone": "mysterious", "summary": "An adventure story."}'
        )

        book_prof, chap_profs = self.analyzer.analyze(self.book)

        # Assertions on BookProfile
        self.assertEqual(book_prof.title, "The Map of Wandering")
        self.assertEqual(book_prof.author, "J. R. Wandering")
        self.assertEqual(book_prof.genre, "Fantasy")
        self.assertEqual(book_prof.overall_tone, "mysterious")
        self.assertEqual(book_prof.summary, "An adventure story.")
        self.assertEqual(book_prof.chapter_ids, ["c1", "c2"])

        # Assertions on ChapterProfiles
        self.assertEqual(len(chap_profs), 2)
        self.assertEqual(chap_profs[0].chapter_id, "c1")
        self.assertEqual(chap_profs[0].title, "Beginning")
        self.assertEqual(chap_profs[0].summary, "The hero enters the forest.")
        self.assertEqual(chap_profs[0].tone, "dark")
        self.assertEqual(chap_profs[0].importance, 0.6)

        self.assertEqual(chap_profs[1].chapter_id, "c2")
        self.assertEqual(chap_profs[1].title, "The Wizard's Offer")
        self.assertEqual(chap_profs[1].summary, "The wizard gives a map.")
        self.assertEqual(chap_profs[1].tone, "mysterious")
        self.assertEqual(chap_profs[1].importance, 0.8)

        # Assert that cache file is created and non-empty
        self.assertTrue(self.analyzer.cache_file.is_file())

    def test_analyzer_caching_behavior(self) -> None:
        # 1. First run generates cache
        self.mock_adapter.add_response(
            '{"title": "Ch 1", "summary": "Start", "tone": "calm", "importance": 0.5}'
        )
        self.mock_adapter.add_response(
            '{"title": "Ch 2", "summary": "Walk", "tone": "calm", "importance": 0.5}'
        )
        self.mock_adapter.add_response(
            '{"genre": "Drama", "overall_tone": "calm", "summary": "Drama story."}'
        )

        first_book_prof, first_chap_profs = self.analyzer.analyze(self.book)

        # 2. Second run should hit cache. We configure the mock to raise exception if called.
        self.mock_adapter.exception = RuntimeError("LLM should not be called on cache hit")

        cached_book_prof, cached_chap_profs = self.analyzer.analyze(self.book)

        self.assertEqual(cached_book_prof.genre, "Drama")
        self.assertEqual(len(cached_chap_profs), 2)
        self.assertEqual(cached_chap_profs[0].summary, "Start")

        # 3. Third run: Modify chapter text, hash should change and trigger a new LLM call
        self.mock_adapter.exception = None
        self.mock_adapter.add_response(
            '{"title": "Ch 1 New", "summary": "New Start", "tone": "intense", "importance": 0.9}'
        )
        self.mock_adapter.add_response(
            '{"title": "Ch 2 New", "summary": "New Walk", "tone": "intense", "importance": 0.9}'
        )
        self.mock_adapter.add_response(
            '{"genre": "Thriller", "overall_tone": "intense", "summary": "Thriller story."}'
        )

        modified_chapters = [
            Chapter(id="c1", title="Beginning", index=0, text="Intense forest monster fight!"),
            self.chapter2
        ]
        modified_book = Book(
            id="book-123",
            source_path=Path("sample.epub"),
            title="The Map of Wandering",
            author="J. R. Wandering",
            chapters=modified_chapters,
        )

        new_book_prof, new_chap_profs = self.analyzer.analyze(modified_book)
        self.assertEqual(new_book_prof.genre, "Thriller")
        self.assertEqual(new_chap_profs[0].summary, "New Start")

    def test_analyzer_graceful_llm_failure(self) -> None:
        # Mock LLM API raising exception
        self.mock_adapter.exception = LLMError("API Connection Timeout")

        book_prof, chap_profs = self.analyzer.analyze(self.book)

        # Should generate fallback profiles
        self.assertEqual(book_prof.genre, "unknown")
        self.assertEqual(book_prof.summary, "Analysis unavailable (LLM or validation failure).")
        self.assertEqual(len(chap_profs), 2)
        self.assertEqual(chap_profs[0].summary, "Analysis unavailable (LLM or validation failure).")
        self.assertEqual(chap_profs[0].importance, 0.5)

    def test_analyzer_graceful_validation_failure(self) -> None:
        # Mock LLM returning invalid structure (missing 'tone' and 'summary' fields)
        self.mock_adapter.add_response(
            '{"title": "Beginning", "importance": 0.6}'
        )

        book_prof, chap_profs = self.analyzer.analyze(self.book)

        # Should fallback gracefully
        self.assertEqual(book_prof.genre, "unknown")
        self.assertEqual(book_prof.summary, "Analysis unavailable (LLM or validation failure).")
        self.assertEqual(len(chap_profs), 2)
        self.assertEqual(chap_profs[0].summary, "Analysis unavailable (LLM or validation failure).")

    def test_markdown_code_block_stripping(self) -> None:
        # Test that LLM responses wrapped in ```json are parsed successfully
        self.mock_adapter.add_response(
            '```json\n{"title": "Beginning", "summary": "The hero enters the forest.", "tone": "dark", "importance": 0.6}\n```'
        )
        self.mock_adapter.add_response(
            '```\n{"title": "The Wizard\'s Offer", "summary": "The wizard gives a map.", "tone": "mysterious", "importance": 0.8}\n```'
        )
        self.mock_adapter.add_response(
            '```json\n{"genre": "Fantasy", "overall_tone": "mysterious", "summary": "An adventure story."}\n```'
        )

        book_prof, chap_profs = self.analyzer.analyze(self.book)
        self.assertEqual(book_prof.genre, "Fantasy")
        self.assertEqual(chap_profs[0].summary, "The hero enters the forest.")
