"""Unit tests of app/services/pdf.py: text, metadata heuristics, outline, and heading search."""

from datetime import date

import pymupdf
import pytest

from app.services import pdf
from support import pdfs

FILLER = "Body text that makes the page long enough for extraction to count it as real text. " * 3


# --- Text and metadata ------------------------------------------------------------------------


def test_extract_the_sample_paper():
    extracted = pdf.extract(pdfs.sample_pdf())

    assert extracted.title == pdfs.SAMPLE_TITLE
    assert extracted.authors == pdfs.SAMPLE_AUTHORS
    assert extracted.year == pdfs.SAMPLE_YEAR
    assert extracted.abstract == pdfs.SAMPLE_ABSTRACT
    assert extracted.page_count == 2
    assert extracted.arxiv_id is None
    assert pdfs.BODY_MARKER in extracted.text and pdfs.BODY_MARKER not in extracted.first_page


def test_title_split_by_a_hyphen_across_lines_is_rejoined():
    data = pdfs.paper_pdf(title_lines=["Scaling Laws for Neural LAN-", "GUAGE Models"])

    assert pdf.extract(data).title == "Scaling Laws for Neural LANGUAGE Models"


@pytest.mark.parametrize(("line", "names"), [
    ("Alice Smith, Bob Jones and Carol White", ["Alice Smith", "Bob Jones", "Carol White"]),
    ("Alice Smith1,2, Bob Jones∗ & Carol White†", ["Alice Smith", "Bob Jones", "Carol White"]),
    ("Ashish Vaswani    Noam Shazeer    Niki Parmar", ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]),
    ("Kaiming He · Xiangyu Zhang", ["Kaiming He", "Xiangyu Zhang"]),
    ("we propose a method", []),  # not capitalized names
])
def test_author_names_are_split_from_a_line(line, names):
    assert pdf._split_names(line) == names


def test_year_next_to_a_venue_beats_years_of_citations():
    page = "BERT\nProceedings of NAACL-HLT 2019\nas in (Vaswani et al., 2017) and (Peters et al., 2018; Radford, 2018)"
    assert pdf._guess_year(page, {}) == 2019


def test_year_falls_back_to_the_most_common_year_then_the_pdf_date():
    assert pdf._guess_year("Cited 2015, 2015 and 2012.", {}) == 2015
    assert pdf._guess_year("No year here.", {"creationDate": "D:20210305120000Z"}) == 2021
    assert pdf._guess_year("No year here.", {}) is None


def test_years_in_the_future_are_ignored():
    next_year = date.today().year + 1
    assert pdf._guess_year(f"Preprint {next_year}. Submitted {next_year}.", {}) is None


@pytest.mark.parametrize("heading", ["Abstract", "ABSTRACT", "A BSTRACT", "Abstract."])
def test_abstract_is_found_after_its_heading(heading):
    body = "We study how lan-\nguage models use retrieved passages, and show that retrieval helps a lot. " * 2
    text = f"Some Title\nAlice Smith\n{heading}\n{body}\n1 Introduction\nIntroduction text."

    abstract = pdf._guess_abstract(text)

    assert abstract.startswith("We study how language models use retrieved passages")  # hyphenation fixed
    assert "Introduction" not in abstract


@pytest.mark.parametrize("end", ["Keywords: retrieval, LLMs", "Index Terms—retrieval", "∗Equal contribution.",
                                 "Preprint. Under review.", "CCS Concepts: Computing"])
def test_abstract_ends_before_keywords_footnotes_and_venue_notes(end):
    body = ("We present a method for retrieval augmented generation that reduces hallucinations "
            "considerably on three benchmarks.")
    assert pdf._guess_abstract(f"Abstract\n{body}\n{end}\nMore text that is not abstract.") == body


def test_too_short_abstract_is_not_trusted():
    assert pdf._guess_abstract("Abstract\nToo short.\n1 Introduction\n...") is None
    assert pdf._guess_abstract("No heading anywhere in this text.") is None


def test_pdf_properties_override_the_layout_guess_unless_they_are_placeholders():
    good = pdf.extract(pdfs.paper_pdf(metadata={"title": "The Real Title From Properties", "author": "Eve Adams and Frank Moore"}))
    placeholder = pdf.extract(pdfs.paper_pdf(metadata={"title": "untitled.pdf"}))

    assert (good.title, good.authors) == ("The Real Title From Properties", ["Eve Adams", "Frank Moore"])
    assert placeholder.title == pdfs.SAMPLE_TITLE


def test_arxiv_margin_stamp_is_preferred_over_a_cited_id():
    data = pdfs.paper_pdf(margin_stamp="arXiv:2106.09685v2 [cs.CL] 16 Oct 2021",
                          first_page_note="Unlike arXiv:1810.04805, our adapters are small.")

    assert pdf.extract(data).arxiv_id == "2106.09685"


def test_cited_arxiv_id_is_reported_when_there_is_no_stamp():
    # The caller then checks the title before trusting it (see test_upload.py).
    data = pdfs.paper_pdf(first_page_note="We build on arXiv:1810.04805v2 for the encoder.")

    assert pdf.extract(data).arxiv_id == "1810.04805"


def test_text_is_read_from_a_limited_number_of_pages():
    # The page limit keeps huge PDFs fast; test_summary.py checks that the cut is disclosed.
    limit = pdf.MAX_PDF_PAGES_FOR_TEXT

    extracted = pdf.extract(pdfs.numbered_pages_pdf(limit + 2))

    assert extracted.page_count == limit + 2
    assert f"Page marker {limit}." in extracted.text
    assert f"Page marker {limit + 1}." not in extracted.text


@pytest.mark.parametrize(("data", "message"), [
    (b"%PDF-1.4 truncated", "The file could not be read as a PDF."),
    (pdfs.encrypted_pdf(), "The PDF is password-protected."),
    (pdfs.blank_pdf(), "No text could be extracted. The PDF may be a scanned image."),
])
def test_unusable_pdfs_raise_a_readable_error(data, message):
    with pytest.raises(pdf.PdfError, match=message):
        pdf.extract(data)


@pytest.mark.parametrize(("title", "page", "expected"), [
    ("Attention Is All You Need!", "Title: attention is all you need\nAuthors", True),
    ("Efficient Fine-Tuning of Models", "Eﬃcient ﬁne-tuning of models", True),  # PDF ligatures
    ("LoRA: Low-Rank Adaptation", "LORA:LOW-RANKADAPTATION OF LARGE LANGUAGE MODELS", True),  # lost spaces
    ("Über Graphen", "ÜBER GRAPHEN und mehr", True),
    ("BERT", "BERT is everywhere", False),  # too short to be a reliable check
    ("Deep Residual Learning", "Attention is all you need", False),
])
def test_title_on_page(title, page, expected):
    assert pdf.title_on_page(title, page) is expected


# --- Section outline ---------------------------------------------------------------------------------


def outline_of(data: bytes) -> list[tuple[int, str, int]]:
    return [(entry.level, entry.title, entry.page) for entry in pdf.extract_outline(data)]


def test_outline_from_bold_numbered_headings():
    assert outline_of(pdfs.sample_pdf()) == [
        (1, "Abstract", 1), (1, "1 Introduction", 1), (1, "2 Method", 2), (1, "3 Experiments", 2),
        (1, "4 Conclusion", 2)]


def test_outline_has_subsections_but_not_sub_subsections_and_ends_at_references():
    sections = [
        ("1 Introduction", FILLER, 1), ("2 Method", FILLER, 2), ("2.1 Retriever", FILLER, 2),
        ("2.1.1 Index Details", FILLER, 2), ("3 Results", FILLER, 2), ("References", "[1] A. Author. 2020.", 3),
        ("A Appendix Tables", FILLER, 3), ("5 Extra Material", FILLER, 3),
    ]

    assert outline_of(pdfs.paper_pdf(sections=sections)) == [
        (1, "Abstract", 1), (1, "1 Introduction", 1), (1, "2 Method", 2), (2, "2.1 Retriever", 2),
        (1, "3 Results", 2), (1, "References", 3)]


def test_outline_prefers_bookmarks_when_there_are_at_least_three():
    toc = [[1, "Introduction", 1], [1, "Method", 2], [2, "Retriever", 2], [3, "Too deep", 2], [1, "Results", 2]]

    assert outline_of(pdfs.paper_pdf(toc=toc)) == [
        (1, "Introduction", 1), (1, "Method", 2), (2, "Retriever", 2), (1, "Results", 2)]


def test_outline_ignores_too_few_bookmarks():
    toc = [[1, "Only bookmark", 1], [1, "Another", 2]]

    assert [title for _, title, _ in outline_of(pdfs.paper_pdf(toc=toc))][:2] == ["Abstract", "1 Introduction"]


def test_outline_from_untrusted_bookmarks_is_bounded():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), FILLER[:80])
    doc.set_toc([[1, f"Section {i} " + "x" * 300, 1] for i in range(300)])

    entries = pdf.extract_outline(doc.tobytes())

    assert len(entries) == pdf.MAX_OUTLINE_ENTRIES
    assert all(len(entry.title) <= pdf.MAX_TITLE_CHARS for entry in entries)


def test_outline_of_a_pdf_without_structure_is_empty():
    assert pdf.extract_outline(pdfs.unstructured_pdf([FILLER, FILLER])) == []


def test_outline_of_an_unreadable_file():
    with pytest.raises(pdf.PdfError):
        pdf.extract_outline(b"not a pdf")


# --- Locating headings named by the model --------------------------------------------------------------


def test_locate_headings_in_reading_order():
    found = pdf.locate_headings(pdfs.sample_pdf(), ["Introduction", "2. Method", "Experiments", "Not In This Paper"])

    assert [spot[0] if spot else None for spot in found] == [1, 2, 2, None]
    # On page 2, "Experiments" is drawn below "Method".
    assert 0 < found[1][1] < found[2][1] < 1


def test_headings_are_searched_forward_from_the_previous_one():
    # The model lists sections in reading order: a heading is not looked for before the previous one.
    found = pdf.locate_headings(pdfs.sample_pdf(), ["Experiments", "Introduction"])

    assert [spot[0] if spot else None for spot in found] == [2, None]


MENTION = "We describe the Retrieval Setup in a later section of this paper, after the method."


@pytest.mark.parametrize(("sections", "expected_page"), [
    # A heading that starts with the title beats a mention in running text, even an earlier one.
    ([("1 Introduction", MENTION, 1), ("2 Method", FILLER, 2), ("3 Retrieval Setup and Index", FILLER, 2)], 2),
    # A heading equal to the title beats both.
    ([("1 Introduction", MENTION, 1), ("2 Retrieval Setup and Index", FILLER, 2),
      ("3 Experiments", FILLER, 2), ("4 Retrieval Setup", FILLER, 3)], 3),
], ids=["heading starting with the title", "heading equal to the title"])
def test_the_best_match_for_a_heading_wins(sections, expected_page):
    [(page, _)] = pdf.locate_headings(pdfs.paper_pdf(sections=sections), ["Retrieval Setup"])

    assert page == expected_page


def test_heading_search_ignores_case_punctuation_and_section_numbers():
    found = pdf.locate_headings(pdfs.sample_pdf(), ["EXPERIMENTS", "4. conclusion"])

    assert [spot[0] for spot in found] == [2, 2]
