from pathlib import Path
import unittest

from pydantic import ValidationError

from app.book import Book, BookMetadata, Chapter, ChapterProfile


class BookModelTests(unittest.TestCase):
    def test_book_contains_nested_chapters_and_metadata(self) -> None:
        chapter = Chapter(id="chapter-1", title="Opening", index=0, text="Once upon a time.")
        metadata = BookMetadata(language="eng", publisher="Example Press")
        book = Book(
            id="book-1",
            source_path=Path("data/book.epub"),
            title="Example Book",
            author="Example Author",
            chapters=[chapter],
            metadata=metadata,
        )

        self.assertEqual(book.chapters[0].title, "Opening")
        self.assertEqual(book.metadata.language, "eng")
        self.assertEqual(book.source_path, Path("data/book.epub"))

    def test_defaults_are_independent(self) -> None:
        first = Book(id="one", source_path="one.epub", title="One", author="Author")
        second = Book(id="two", source_path="two.epub", title="Two", author="Author")

        first.chapters.append(Chapter(id="one-chapter", title="One", index=0, text="Text"))
        self.assertEqual(second.chapters, [])
        self.assertIsNot(first.metadata, second.metadata)

    def test_invalid_values_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Chapter(id="chapter-1", title="", index=0, text="Text")
        with self.assertRaises(ValidationError):
            Chapter(id="chapter-1", title="Title", index=-1, text="Text")
        with self.assertRaises(ValidationError):
            Book(id="", source_path="book.epub", title="Title", author="Author")

    def test_chapter_profile_validation(self) -> None:
        # Valid importance values should pass
        cp_zero = ChapterProfile(chapter_id="1", title="Ch1", summary="Sum", tone="Neutral", importance=0.0)
        cp_mid = ChapterProfile(chapter_id="1", title="Ch1", summary="Sum", tone="Neutral", importance=0.5)
        cp_one = ChapterProfile(chapter_id="1", title="Ch1", summary="Sum", tone="Neutral", importance=1.0)
        
        self.assertEqual(cp_zero.importance, 0.0)
        self.assertEqual(cp_mid.importance, 0.5)
        self.assertEqual(cp_one.importance, 1.0)

        # Invalid importance values should raise ValidationError
        with self.assertRaises(ValidationError):
            ChapterProfile(chapter_id="1", title="Ch1", summary="Sum", tone="Neutral", importance=-0.1)
        with self.assertRaises(ValidationError):
            ChapterProfile(chapter_id="1", title="Ch1", summary="Sum", tone="Neutral", importance=1.1)


if __name__ == "__main__":
    unittest.main()