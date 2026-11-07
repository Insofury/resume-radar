"""Turn uploaded resume files (PDF, DOCX, TXT/MD) into plain text - in memory only."""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_PAGES = 10
MAX_DOCX_XML_BYTES = 15 * 1024 * 1024  # guards against zip bombs
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ParseError(ValueError):
    """The file can't be read; the message is safe to show to the user."""


def extract_pdf(data: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ParseError("This PDF is password-protected. Please upload an unlocked copy.") from exc
        pages = reader.pages
        texts = [page.extract_text() or "" for page in list(pages)[:MAX_PDF_PAGES]]
    except ParseError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise ParseError("We couldn't read this PDF. Try exporting it again or paste the text instead.") from exc
    return "\n".join(texts), len(pages)


def extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise ParseError("This Word document is too large to process.")
            root = ElementTree.fromstring(archive.read(info))
    except ParseError:
        raise
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ParseError("We couldn't read this Word file. Save it as .docx or PDF and try again.") from exc

    paragraphs = []
    for para in root.iter(f"{_W}p"):
        parts = []
        for node in para.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        text = "".join(parts).strip()
        if not text:
            paragraphs.append("")
            continue
        is_list_item = para.find(f"{_W}pPr/{_W}numPr") is not None
        paragraphs.append(f"• {text}" if is_list_item else text)
    return "\n".join(paragraphs)


def extract_text(filename: str, data: bytes) -> dict:
    """Return {"text", "kind", "pages"} for an uploaded file or raise ParseError."""
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        text, pages = extract_pdf(data)
        kind = "pdf"
    elif name.endswith(".docx"):
        text, pages, kind = extract_docx(data), None, "docx"
    elif name.endswith((".txt", ".md")):
        text, pages, kind = data.decode("utf-8", errors="replace"), None, "text"
    else:
        raise ParseError("Unsupported file type. Upload a PDF, DOCX or TXT file.")

    if len(text.strip()) < 50:
        if kind == "pdf":
            raise ParseError(
                "We found almost no text in this PDF - it may be a scanned image. "
                "Export it from your editor as a text PDF, or paste the text instead."
            )
        raise ParseError("This file looks empty. Paste your resume text instead.")
    return {"text": text, "kind": kind, "pages": pages}
