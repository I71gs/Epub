from pathlib import Path
import tempfile
import unittest
import zipfile

import pymupdf

from app.book import BookParser


class BookParserTests(unittest.TestCase):
    def test_parses_epub_metadata_and_spine_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.epub"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    '<container><rootfiles><rootfile full-path="OEBPS/content.opf" /></rootfiles></container>',
                )
                archive.writestr(
                    "OEBPS/content.opf",
                    '<package><metadata xmlns:dc="dc"><dc:title>Sample</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language></metadata><manifest><item id="c1" href="chapter.xhtml" media-type="application/xhtml+xml" /></manifest><spine><itemref idref="c1" /></spine></package>',
                )
                archive.writestr(
                    "OEBPS/chapter.xhtml",
                    "<html><head><title>Chapter One</title></head><body><h1>Chapter One</h1><p>Hello reader.</p></body></html>",
                )

            book = BookParser().parse(path)

        self.assertEqual(book.title, "Sample")
        self.assertEqual(book.author, "Author")
        self.assertEqual(book.metadata.language, "en")
        self.assertEqual(book.chapters[0].title, "Chapter One")
        self.assertIn("Hello reader.", book.chapters[0].text)

    def test_parses_pdf_pages_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pdf"
            document = pymupdf.open()
            document.set_metadata({"title": "PDF Sample", "author": "PDF Author"})
            page = document.new_page()
            page.insert_text((72, 72), "Chapter One\nHello PDF")
            document.save(path)
            document.close()

            book = BookParser().parse(path)

        self.assertEqual(book.title, "PDF Sample")
        self.assertEqual(book.author, "PDF Author")
        self.assertEqual(len(book.chapters), 1)
        self.assertIn("Hello PDF", book.chapters[0].text)

    def test_rejects_unsupported_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.touch()
            with self.assertRaises(ValueError):
                BookParser().parse(path)


if __name__ == "__main__":
    unittest.main()