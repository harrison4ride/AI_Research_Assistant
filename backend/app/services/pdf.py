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


# --- Section outline (for the reader's left panel) ------------------------------

SECTION_NUMBER_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.?$")
NUMBERED_HEADING_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-Z][^\n]{1,80})$")
NAMED_HEADING_RE = re.compile(
    r"^(abstract|introduction|related work|background|methods?|methodology|approach|"
    r"experiments?|experimental setup|results|discussion|analysis|conclusions?|limitations|"
    r"acknowledge?ments|references|bibliography)$",
    re.IGNORECASE,
)
END_SECTIONS = {"references", "bibliography"}
# Headings that stay unnumbered even in papers with numbered sections. Other named
# headings ("Methods", "Results") in such papers are usually table or figure labels.
UNNUMBERED_SECTIONS = {"abstract", "limitations", "acknowledgments", "acknowledgements", "references", "bibliography"}

# Limits for untrusted PDFs: an outline is shown in full and sent to the model.
MAX_OUTLINE_ENTRIES = 120
MAX_TITLE_CHARS = 200


@dataclass
class OutlineEntry:
    level: int  # 1 = section, 2 = subsection
    title: str
    page: int  # 1-based
    top: float  # position on the page, 0 = top, 1 = bottom


@dataclass
class _Line:
    page: int
    y: float
    x0: float
    x1: float
    text: str
    size: float
    bold: bool
    height: float


def _clean_title(title: str) -> str:
    """Normalize PDF text (ligatures such as "ﬁ", odd spacing) and bound its length."""
    return unicodedata.normalize("NFKC", " ".join(str(title).split()))[:MAX_TITLE_CHARS]


def _bookmark_top(doc: pymupdf.Document, page: int, dest: object) -> float:
    """Where a bookmark points on its page: 0 = top, 1 = bottom."""
    if not isinstance(dest, dict) or page > doc.page_count:
        return 0.0
    to = dest.get("to")
    height = doc[page - 1].rect.height
    if to is None or not height or (to.x == 0 and to.y == 0):
        return 0.0  # /Fit or a destination without a position: the page's top
    # PyMuPDF reports named destinations (LaTeX hyperref) in PDF coordinates,
    # whose origin is the bottom of the page, and explicit ones from the top.
    top = 1 - to.y / height if dest.get("kind") == pymupdf.LINK_NAMED else to.y / height
    return min(max(top, 0.0), 1.0)


def _outline_from_bookmarks(doc: pymupdf.Document) -> list[OutlineEntry]:
    toc = [(level, title, page, dest) for level, title, page, dest in doc.get_toc(simple=False)
           if 1 <= page <= doc.page_count and level <= 2]
    if len(toc) > MAX_OUTLINE_ENTRIES:
        toc = [entry for entry in toc if entry[0] == 1]  # sections only
    entries = []
    for level, title, page, dest in toc[:MAX_OUTLINE_ENTRIES]:
        if title := _clean_title(title):
            entries.append(OutlineEntry(level, title, page, _bookmark_top(doc, page, dest)))
    return entries


def _page_lines(page: pymupdf.Page, pno: int, sizes: Counter) -> list[_Line]:
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            if abs(line["dir"][0] - 1) > 0.01:
                continue
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            for s in spans:
                sizes[round(s["size"], 1)] += len(s["text"])
            bold = all(
                (s["flags"] & 16) or re.search(r"bold|black|semibold|medi", s["font"], re.IGNORECASE)
                for s in spans
            )
            lines.append(_Line(
                page=pno + 1, y=line["bbox"][1], x0=line["bbox"][0], x1=line["bbox"][2],
                text=" ".join("".join(s["text"] for s in spans).split()),
                size=max(s["size"] for s in spans), bold=bool(bold), height=page.rect.height,
            ))
    return lines


def _join_split_numbers(lines: list[_Line]) -> list[_Line]:
    """Some templates (e.g. ACL) set "3" and "BERT" as separate lines side by side."""
    merged, used = [], set()
    for i, line in enumerate(lines):
        if i in used:
            continue
        if line.bold and SECTION_NUMBER_RE.match(line.text):
            for j, other in enumerate(lines):
                if (j != i and j not in used and other.bold and abs(other.y - line.y) < 2
                        and 0 <= other.x0 - line.x1 < 40):
                    other.text = f"{line.text.rstrip('.')} {other.text}"
                    used.add(i)
                    break
            if i in used:
                continue
        merged.append(line)
    return merged


def _outline_from_headings(doc: pymupdf.Document) -> list[OutlineEntry]:
    """Detect numbered or well-known section headings by emphasis (bold or larger text)."""
    sizes: Counter = Counter()
    pages = []
    for pno in range(doc.page_count):
        # Joining runs per page, so its cost grows with lines per page, not per document.
        pages.append(_join_split_numbers(_page_lines(doc[pno], pno, sizes)))
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    lines = [line for page in pages for line in page]

    def emphasized(line: _Line) -> bool:
        return line.bold or line.size >= body + 0.8

    numbered_count = sum(1 for line in lines if emphasized(line) and NUMBERED_HEADING_RE.match(line.text))
    entries: list[OutlineEntry] = []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        text = line.text
        if len(text) > 90 or text.endswith((".", ",", ";", ":")) or not emphasized(line):
            continue
        if m := NUMBERED_HEADING_RE.match(text):
            number, rest = m.groups()
            if int(number.split(".")[0]) > 20 or len(re.findall(r"[A-Za-z]", rest)) < 3:
                continue
            if number.count(".") > 1:
                continue  # sub-subsections: too fine for the outline
            level, title = number.count(".") + 1, f"{number} {rest}"
            # A long heading can wrap: take the next line too if it continues it.
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if (nxt and nxt.page == line.page and abs(nxt.x0 - line.x0) < 40
                    and 0 < nxt.y - line.y < 2 * line.size and abs(nxt.size - line.size) < 0.5
                    and nxt.bold == line.bold and not NUMBERED_HEADING_RE.match(nxt.text)
                    and not NAMED_HEADING_RE.match(nxt.text) and len(nxt.text) <= 80
                    and not nxt.text.endswith(".")):
                title = f"{title} {nxt.text}"
        elif NAMED_HEADING_RE.match(text):
            if numbered_count >= 3 and text.lower() not in UNNUMBERED_SECTIONS:
                continue
            level, title = 1, text.title() if text.isupper() else text
        else:
            continue
        title = _clean_title(title)
        key = title.lower()
        if key in seen:  # running headers repeat on every page
            continue
        seen.add(key)
        entries.append(OutlineEntry(level, title, line.page, line.y / line.height if line.height else 0.0))
        if key in END_SECTIONS or len(entries) >= MAX_OUTLINE_ENTRIES:
            break
    return entries


def extract_outline(data: bytes) -> list[OutlineEntry]:
    """The paper's sections, from its bookmarks if it has them, else from its headings."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfError("The file could not be read as a PDF.") from exc
    with doc:
        bookmarks = _outline_from_bookmarks(doc)
        return bookmarks if len(bookmarks) >= 3 else _outline_from_headings(doc)


LEADING_NUMBER_RE = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){0,2}\.?\s+")


def locate_headings(data: bytes, titles: list[str]) -> list[tuple[int, float] | None]:
    """(page, top) of each heading, searching forward through the document in order.

    Compares ligature-normalized, case-folded text without spaces, punctuation, or
    a leading section number. For each title the best match wins: a heading line
    (bold or larger than body text) equal to the title, then one starting with it,
    then a mention inside running text.
    """
    doc = pymupdf.open(stream=data, filetype="pdf")
    with doc:
        sizes: Counter = Counter()
        pages = [_page_lines(doc[pno], pno, sizes) for pno in range(doc.page_count)]
        body = sizes.most_common(1)[0][0] if sizes else 10.0
        keyed = [
            [(_squash(LEADING_NUMBER_RE.sub("", line.text)), line) for line in page] for page in pages
        ]

        found: list[tuple[int, float] | None] = []
        start = 0
        for title in titles:
            target = _squash(LEADING_NUMBER_RE.sub("", title))
            best: dict[int, tuple[int, float]] = {}  # rank -> first spot with that rank
            if len(target) >= 3:
                for pno in range(start, len(pages)):
                    for text, line in keyed[pno]:
                        heading = line.bold or line.size >= body + 0.8
                        rank = (0 if heading and text == target
                                else 1 if heading and text.startswith(target)
                                else 2 if target in text else None)
                        if rank is not None and rank not in best:
                            best[rank] = (pno, line.y / line.height if line.height else 0.0)
                    if 0 in best:
                        break
            hit = best[min(best)] if best else None
            if hit:
                start = hit[0]
                found.append((hit[0] + 1, hit[1]))
            else:
                found.append(None)
        return found
