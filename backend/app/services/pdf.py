"""PDF text extraction and best-effort metadata detection (PyMuPDF)."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import pymupdf

# New-style arXiv ids (1706.03762, 2106.09685v2). The margin stamp on arXiv PDFs
# carries a category ("arXiv:1706.03762v7 [cs.CL]"); citations usually don't.
ARXIV_STAMP_RE = re.compile(r"arXiv:\s?(\d{4}\.\d{4,5})(?:v\d+)?\s*\[[\w.-]+\]", re.IGNORECASE)
ARXIV_ID_RE = re.compile(r"arXiv:\s?(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[5-9]\d|20\d\d)\b")
ABSTRACT_START_RE = re.compile(r"(?:^|\n)\s*A\s?BSTRACT\b[\s.:—–-]*|(?:^|\n)\s*Abstract\b[\s.:—–-]*", re.MULTILINE)
ABSTRACT_END_RE = re.compile(
    r"\n\s*(?:(?:1|I)\.?\s+Introduction|(?:1|I)\.?\s+INTRODUCTION|INTRODUCTION\s*\n|Introduction\s*\n"
    r"|Keywords\b|Key\s?words\b|Index Terms\b|CCS Concepts\b|ACM Reference Format\b"
    # Page-1 footnotes and venue stamps that follow the abstract on the same page.
    r"|[∗*†‡§]\s*\w|\d+(?:st|nd|rd|th) Conference\b|Preprint\b|Proceedings of\b|arXiv:\d)",
)
# Years next to venue words ("Proceedings of NAACL-HLT 2019", "NIPS 2017") beat
# years that merely appear in citations on page 1.
VENUE_YEAR_RE = re.compile(
    r"(?:Proceedings|Conference|Workshop|Symposium|Journal|Transactions|Copyright|©|Published|"
    r"Accepted|Preprint|ICLR|ICML|NeurIPS|NIPS|CVPR|ICCV|ECCV|ACL|EMNLP|NAACL|AAAI|IJCAI|KDD|SIGIR)"
    r"[^\n]{0,80}?\b(19[5-9]\d|20\d\d)\b"
)
AFFILIATION_WORDS = re.compile(
    r"universit|institut|department|dept\.|laborator|\blab\b|school|college|cent(er|re)\b|"
    r"research|inc\.|corp|company|ltd|google|microsoft|meta\b|facebook|openai|deepmind|amazon|"
    r"nvidia|ibm|academy|hospital|street|road|\busa\b|china|germany|canada|france|japan|korea",
    re.IGNORECASE,
)
# Placeholder titles that PDF producers write into the metadata.
JUNK_META_TITLE = re.compile(r"^(untitled|microsoft word|document\d*|paper|main|arxiv|\S+\.(pdf|docx?|tex|dvi))", re.I)

MAX_PDF_PAGES_FOR_TEXT = 300


class PdfError(Exception):
    """The file is not a readable PDF, or contains no extractable text."""


@dataclass
class ExtractedPdf:
    text: str
    page_count: int
    first_page: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    arxiv_id: str | None = None


def _clean(text: str) -> str:
    # Re-join words hyphenated across line breaks, then collapse whitespace.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return " ".join(text.split())


def _horizontal_lines(page: pymupdf.Page) -> list[tuple[float, float, str]]:
    """(max font size, y position, text) for each horizontal text line on the page."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            # Skip rotated text such as the arXiv id stamped in the left margin.
            if abs(line["dir"][0] - 1) > 0.01:
                continue
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = " ".join("".join(s["text"] for s in spans).split())
            lines.append((max(s["size"] for s in spans), line["bbox"][1], text))
    return lines


def _guess_title(lines: list[tuple[float, float, str]], page_height: float) -> tuple[str | None, int]:
    """Largest-font text in the top half of page 1. Returns (title, index of last title line)."""
    candidates = [
        (i, size) for i, (size, y, text) in enumerate(lines)
        if y < page_height * 0.5 and len(text) > 3 and re.search(r"[A-Za-z]{3}", text)
    ]
    if not candidates:
        return None, -1
    max_size = max(size for _, size in candidates)
    title_idx = [i for i, size in candidates if size >= max_size - 0.6]
    # Title lines are consecutive; stop at the first gap.
    run = [title_idx[0]]
    for i in title_idx[1:]:
        if i != run[-1] + 1:
            break
        run.append(i)
    title = ""
    for i in run:
        line = lines[i][2]
        # Re-join a word hyphenated across title lines ("LAN-" + "GUAGE").
        title = title[:-1] + line if title.endswith("-") else f"{title} {line}"
    title = title.strip()
    return (title if 5 <= len(title) <= 300 else None), run[-1]


def _split_names(line: str) -> list[str]:
    line = re.sub(r"[\d∗*†‡§¶#,]+(?=\s|$|,)", ",", line)  # footnote markers
    parts = re.split(r",|\band\b|&|\s{2,}|·", line)
    names = []
    for part in parts:
        name = " ".join(part.split()).strip(" .;:")
        words = name.split()
        if 2 <= len(words) <= 5 and all(w[0].isupper() for w in words if w[0].isalpha()):
            names.append(name)
    return names


def _guess_authors(lines: list[tuple[float, float, str]], title_end: int) -> list[str]:
    """Name-like lines between the title and the abstract heading."""
    authors: list[str] = []
    for _, _, text in lines[title_end + 1 : title_end + 25]:
        if re.match(r"^\s*a\s?bstract\b", text, re.IGNORECASE):
            break
        if "@" in text or AFFILIATION_WORDS.search(text) or len(text) > 200:
            continue
        for name in _split_names(text):
            if name not in authors:
                authors.append(name)
    return authors[:30]


def _guess_abstract(text: str) -> str | None:
    start = ABSTRACT_START_RE.search(text)
    if not start:
        return None
    body = text[start.end():]
    end = ABSTRACT_END_RE.search(body)
    abstract = _clean(body[: end.start()] if end else body[:3000])
    if len(abstract) < 100:
        return None
    return abstract[:3000]


def _guess_year(first_page: str, metadata: dict) -> int | None:
    this_year = date.today().year
    venue_years = [int(y) for y in VENUE_YEAR_RE.findall(first_page) if int(y) <= this_year]
    if venue_years:
        return Counter(venue_years).most_common(1)[0][0]
    years = [int(y) for y in YEAR_RE.findall(first_page) if int(y) <= this_year]
    if years:
        return Counter(years).most_common(1)[0][0]
    created = metadata.get("creationDate") or ""
    m = re.match(r"D:(\d{4})", created)
    return int(m.group(1)) if m and int(m.group(1)) <= this_year else None


def extract(data: bytes) -> ExtractedPdf:
    """Extract full text plus best-guess title, authors, year, and abstract."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several exception types for bad files
        raise PdfError("The file could not be read as a PDF.") from exc
    with doc:
        if doc.needs_pass:
            raise PdfError("The PDF is password-protected.")
        if doc.page_count == 0:
            raise PdfError("The PDF has no pages.")
        pages = [doc[i].get_text("text") for i in range(min(doc.page_count, MAX_PDF_PAGES_FOR_TEXT))]
        text = "\n\n".join(p.strip() for p in pages).strip()
        if len(text) < 200:
            raise PdfError("No text could be extracted. The PDF may be a scanned image.")

        first = doc[0]
        first_text = pages[0]
        lines = _horizontal_lines(first)
        metadata = doc.metadata or {}

        # arXiv stamps the id on page 1; ids further in are usually citations.
        # The caller must still verify the id (see title_on_page).
        arxiv_match = ARXIV_STAMP_RE.search(first_text) or ARXIV_ID_RE.search(first_text)
        arxiv_id = arxiv_match.group(1) if arxiv_match else None

        meta_title = (metadata.get("title") or "").strip()
        title, title_end = _guess_title(lines, first.rect.height)
        if meta_title and not JUNK_META_TITLE.match(meta_title) and len(meta_title) > 8:
            title = meta_title

        meta_author = (metadata.get("author") or "").strip()
        authors = _guess_authors(lines, title_end) if title_end >= 0 else []
        if meta_author and len(meta_author) > 3:
            authors = [a.strip() for a in re.split(r";|,|\band\b", meta_author) if a.strip()] or authors

        return ExtractedPdf(
            text=text,
            page_count=doc.page_count,
            first_page=first_text,
            title=title,
            authors=authors,
            year=_guess_year(first_text, metadata),
            abstract=_guess_abstract("\n".join(pages[:2])),
            arxiv_id=arxiv_id,
        )


def _squash(text: str) -> str:
    # NFKC expands ligature glyphs that PDFs keep ("ﬁ" -> "fi"); \W keeps non-ASCII letters.
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", text).casefold())


def title_on_page(title: str, page_text: str) -> bool:
    """True if `title` appears on the page, ignoring case, spacing, and punctuation."""
    squashed = _squash(title)
    return len(squashed) >= 8 and squashed in _squash(page_text)
