"""Book parsing for supported PDF and EPUB source files."""

from __future__ import annotations

from html.parser import HTMLParser
from hashlib import sha256
from pathlib import Path
import posixpath
import re
from typing import Iterable
import zipfile
from xml.etree import ElementTree

import pymupdf

from app.book.models import Book, BookMetadata, Chapter
from app.core.logging_config import get_logger


class _DocumentTextParser(HTMLParser):
    """Extract readable text and the first heading from one EPUB document."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._heading_parts: list[str] = []
        self._heading_depth = 0
        self._title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and not self._heading_parts:
            self._heading_depth = 1
        elif self._heading_depth:
            self._heading_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._heading_depth:
            self._heading_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        self._parts.append(text)
        if self._heading_depth:
            self._heading_parts.append(text)
        if self._in_title:
            self._title_parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._parts).strip()

    @property
    def title(self) -> str | None:
        title = " ".join(self._heading_parts).strip() or " ".join(self._title_parts).strip()
        return title or None


class BookParser:
    """Parse supported source files into the application's book model."""

    _SUPPORTED_SUFFIXES = {".epub", ".pdf"}

    def __init__(self) -> None:
        self._logger = get_logger(__name__)

    def parse(self, source_path: str | Path) -> Book:
        """Parse one PDF or EPUB source file."""
        path = Path(source_path)
        self._validate_source(path)
        self._logger.info("Parsing book source: %s", path)
        if path.suffix.lower() == ".epub":
            return self._parse_epub(path)
        return self._parse_pdf(path)

    def _parse_epub(self, path: Path) -> Book:
        with zipfile.ZipFile(path) as archive:
            opf_path = self._opf_path(archive)
            opf_root = ElementTree.fromstring(archive.read(opf_path))
            metadata = self._epub_metadata(opf_root)
            manifest = self._epub_manifest(opf_root, opf_path)
            spine = self._epub_spine(opf_root)
            chapters: list[Chapter] = []
            for item_id in spine:
                item_path = manifest.get(item_id)
                if item_path is None:
                    continue
                document = _DocumentTextParser()
                document.feed(archive.read(item_path).decode("utf-8", errors="replace"))
                if document.text:
                    chapters.append(
                        Chapter(
                            id=self._chapter_id(path, len(chapters)),
                            title=document.title or f"Chapter {len(chapters) + 1}",
                            index=len(chapters),
                            text=document.text,
                        )
                    )
        if not chapters:
            raise ValueError(f"No readable chapters found in EPUB: {path}")
        title = metadata.title or path.stem
        author = metadata.author or "Unknown"
        return Book(
            id=self._book_id(path),
            source_path=path,
            title=title,
            author=author,
            chapters=chapters,
            metadata=metadata.model_copy(update={"title": title, "author": author}),
        )

    def _parse_pdf(self, path: Path) -> Book:
        document = pymupdf.open(path)
        try:
            raw_metadata = document.metadata or {}
            title = (raw_metadata.get("title") or "").strip() or path.stem
            author = (raw_metadata.get("author") or "").strip() or "Unknown"
            chapters = []
            for index, page in enumerate(document):
                text = page.get_text("text").strip()
                if not text:
                    continue
                first_line = next((line.strip() for line in text.splitlines() if line.strip()), None)
                chapters.append(
                    Chapter(
                        id=self._chapter_id(path, len(chapters)),
                        title=first_line or f"Page {index + 1}",
                        index=len(chapters),
                        text=text,
                    )
                )
        finally:
            document.close()
        if not chapters:
            raise ValueError(f"No readable text found in PDF: {path}")
        metadata = BookMetadata(title=title, author=author, language=raw_metadata.get("language"))
        return Book(
            id=self._book_id(path),
            source_path=path,
            title=title,
            author=author,
            chapters=chapters,
            metadata=metadata,
        )

    @staticmethod
    def _validate_source(path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Book source does not exist: {path}")
        if path.suffix.lower() not in BookParser._SUPPORTED_SUFFIXES:
            raise ValueError("Book source must be a PDF or EPUB file")

    @staticmethod
    def _opf_path(archive: zipfile.ZipFile) -> str:
        root = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == "rootfile":
                full_path = element.attrib.get("full-path")
                if full_path:
                    return full_path
        raise ValueError("EPUB container does not declare an OPF package")

    @staticmethod
    def _epub_metadata(root: ElementTree.Element) -> BookMetadata:
        values: dict[str, str] = {}
        for element in root.iter():
            name = element.tag.rsplit("}", 1)[-1]
            if name in {"title", "creator", "language", "publisher", "identifier", "description"}:
                text = " ".join((element.text or "").split())
                if text:
                    values.setdefault({"creator": "author"}.get(name, name), text)
        return BookMetadata(**values)

    @staticmethod
    def _epub_manifest(root: ElementTree.Element, opf_path: str) -> dict[str, str]:
        base = posixpath.dirname(opf_path)
        result = {}
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == "item":
                item_id = element.attrib.get("id")
                href = element.attrib.get("href")
                media_type = element.attrib.get("media-type", "")
                if item_id and href and ("html" in media_type or "xhtml" in media_type):
                    result[item_id] = posixpath.normpath(posixpath.join(base, href))
        return result

    @staticmethod
    def _epub_spine(root: ElementTree.Element) -> Iterable[str]:
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == "itemref" and element.attrib.get("idref"):
                yield element.attrib["idref"]

    @staticmethod
    def _book_id(path: Path) -> str:
        return sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]

    @classmethod
    def _chapter_id(cls, path: Path, index: int) -> str:
        return f"{cls._book_id(path)}-{index}"


__all__ = ["BookParser"]