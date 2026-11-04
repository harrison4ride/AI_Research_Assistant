"""Test PDFs, generated with PyMuPDF (already an app dependency) so no binary files are committed.

Run as a script to write the sample paper to stdout (the Playwright tests use this):
    uv run python tests/support/pdfs.py sample > sample.pdf
"""

import sys
from functools import cache

import pymupdf

PAGE_WIDTH, PAGE_HEIGHT = 612, 792  # US Letter, in points
LEFT = 72

SAMPLE_TITLE = "Retrieval Helps Language Models Stay Factual"
SAMPLE_TITLE_LINES = ["Retrieval Helps Language Models", "Stay Factual"]
SAMPLE_AUTHORS = ["Alice Smith", "Bob Jones", "Carol White"]
SAMPLE_YEAR = 2023
SAMPLE_ABSTRACT = (
    "We study how retrieving external documents improves the factual accuracy of large language "
    "models. Our method retrieves passages with a dense retriever and conditions generation on them, "
    "which reduces hallucination on three question answering benchmarks by a large margin."
)
# A sentence that only appears in the body (page 2), to check that the LLM gets the full text.
BODY_MARKER = "The retriever indexes 21 million Wikipedia passages."
SAMPLE_SECTIONS = [
    # (heading, body, page): page 1 holds the front matter and the introduction.
    ("1 Introduction",
     "Large language models often state facts that are wrong. Earlier work by Lewis et al. (2020) and "
     "Guu et al. (2020) added retrieval to pre-training. We revisit the idea for instruction-tuned models "
     "and measure how often retrieval removes unsupported claims.", 1),
    ("2 Method",
     f"{BODY_MARKER} For each question we retrieve the top five passages and prepend them to the prompt. "
     "The generator is fine-tuned to cite the passage that supports each sentence.", 2),
    ("3 Experiments",
     "We evaluate on Natural Questions, TriviaQA, and WebQuestions. Retrieval improves exact match by "
     "eleven points on average and halves the rate of unsupported statements.", 2),
    ("4 Conclusion",
     "Retrieval is a simple and effective way to keep language models factual. Future work should study "
     "retrieval over private document collections.", 2),
]
SAMPLE_SECTION_TITLES = [heading for heading, _, _ in SAMPLE_SECTIONS]
SAMPLE_VENUE_LINE = "Published in Proceedings of ACL 2023."


def _paragraph(page: pymupdf.Page, y: float, text: str, size: float = 10, font: str = "helv") -> float:
    """Write `text` as wrapped lines starting at `y`; return the y below it."""
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > 90:
            page.insert_text((LEFT, y), line, fontsize=size, fontname=font)
            y += size * 1.35
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        page.insert_text((LEFT, y), line, fontsize=size, fontname=font)
        y += size * 1.35
    return y


def paper_pdf(
    *,
    title_lines: list[str] | None = None,
    authors_line: str = "Alice Smith, Bob Jones and Carol White",
    abstract: str = SAMPLE_ABSTRACT,
    sections: list[tuple[str, str, int]] | None = None,
    venue_line: str | None = SAMPLE_VENUE_LINE,
    margin_stamp: str | None = None,
    first_page_note: str | None = None,
    metadata: dict[str, str] | None = None,
    toc: list[list] | None = None,
) -> bytes:
    """A two-page paper laid out like a conference paper (bold headings, larger title)."""
    title_lines = SAMPLE_TITLE_LINES if title_lines is None else title_lines
    sections = SAMPLE_SECTIONS if sections is None else sections
    doc = pymupdf.open()
    page_count = max([2, *(page for *_, page in sections)])
    for _ in range(page_count):
        doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    # Fetch pages only now: PyMuPDF invalidates page objects when pages are added.
    pages = [doc[i] for i in range(page_count)]
    first = pages[0]

    y = 90.0
    for line in title_lines:
        first.insert_text((LEFT, y), line, fontsize=20, fontname="hebo")
        y += 26
    y += 10
    first.insert_text((LEFT, y), authors_line, fontsize=11, fontname="helv")
    y += 16
    first.insert_text((LEFT, y), "Department of Computer Science, Example University", fontsize=10, fontname="helv")
    y += 14
    first.insert_text((LEFT, y), "{alice,bob,carol}@example.edu", fontsize=10, fontname="helv")
    y += 30
    first.insert_text((LEFT, y), "Abstract", fontsize=12, fontname="hebo")
    y = _paragraph(first, y + 18, abstract) + 16

    positions = {i: 90.0 for i in range(1, len(pages))}
    positions[0] = y
    for heading, body, page_number in sections:
        index = page_number - 1
        page = pages[index]
        y = positions[index]
        page.insert_text((LEFT, y), heading, fontsize=12, fontname="hebo")
        positions[index] = _paragraph(page, y + 18, body) + 14

    if first_page_note:
        _paragraph(first, positions[0] + 10, first_page_note)
    if venue_line:
        first.insert_text((LEFT, 760), venue_line, fontsize=8, fontname="helv")
    if margin_stamp:
        # arXiv stamps its id vertically in the left margin.
        first.insert_text((30, 620), margin_stamp, fontsize=14, fontname="helv", rotate=90)
    if metadata:
        doc.set_metadata(metadata)
    if toc:
        doc.set_toc(toc)
    return doc.tobytes()


@cache
def sample_pdf() -> bytes:
    """The default sample paper: its expected metadata is in the SAMPLE_* constants.

    Cached because PyMuPDF writes a random document ID, so two builds differ in a few
    bytes; tests of "the same file" need the very same bytes.
    """
    return paper_pdf()


def unstructured_pdf(paragraphs: list[str], start_y: float = 430) -> bytes:
    """Plain text in one font size, starting in the lower half of page 1.

    There is no title candidate (nothing large in the top half) and no heading.
    """
    doc = pymupdf.open()
    doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = start_y
    for text in paragraphs:
        if y > PAGE_HEIGHT - 80:
            doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = 90
        y = _paragraph(doc[-1], y, text) + 12
    return doc.tobytes()


def blank_pdf() -> bytes:
    """A valid PDF without any text, like a scan without OCR."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.draw_rect(pymupdf.Rect(100, 100, 300, 300), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    return doc.tobytes()


def encrypted_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    _paragraph(page, 90, "Confidential research notes. " * 30)
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="user-secret")


def corrupt_pdf() -> bytes:
    """Starts like a PDF but is not one."""
    return b"%PDF-1.7\n" + b"this is not really a pdf " * 40


if __name__ == "__main__":
    if sys.argv[1:] != ["sample"]:
        sys.exit("usage: pdfs.py sample > sample.pdf")
    sys.stdout.buffer.write(sample_pdf())
