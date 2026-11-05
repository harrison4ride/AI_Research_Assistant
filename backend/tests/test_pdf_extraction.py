"""Unit tests of app/services/pdf.py: text, metadata heuristics, outline, and heading search."""

from datetime import date

import pymupdf
import pytest

from app.services import pdf
from support import pdfs
from support.pdfs import LEFT, SAMPLE_ABSTRACT, SAMPLE_AUTHORS, Text, layout_pdf, wrapped

FILLER = "Body text that makes the page long enough for extraction to count it as real text. " * 3
TITLE = "Retrieval Helps Language Models Stay Factual"
AUTHORS_LINE = "Alice Smith, Bob Jones and Carol White"


def first_page(*lines: Text) -> list[Text]:
    """Page 1 of a paper with the given lines at the top, then the abstract and the introduction."""
    return [*lines, Text(330, "Abstract", 12, "hebo"), *wrapped(348, SAMPLE_ABSTRACT),
            Text(410, "1 Introduction", 12, "hebo"), *wrapped(428, FILLER)]


def width(text: str, size: float, font: str) -> float:
    return pymupdf.get_text_length(text, fontname=font, fontsize=size)


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


def test_the_text_is_every_page_in_order_separated_by_blank_lines():
    data = pdfs.sample_pdf()
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        pages = [page.get_text().strip() for page in doc]

    assert pdf.extract(data).text == "\n\n".join(pages)


def test_title_split_by_a_hyphen_across_lines_is_rejoined():
    data = pdfs.paper_pdf(title_lines=["Scaling Laws for Neural LAN-", "GUAGE Models"])

    assert pdf.extract(data).title == "Scaling Laws for Neural LANGUAGE Models"


@pytest.mark.parametrize("title_lines", [
    ["Attention Is All You", "Need"],  # a short last line
    ["LORA: LOW-RANK ADAPTATION OF", "LARGE LANGUAGE MODELS"],  # in capitals
])
def test_titles_of_every_shape_are_read_whole(title_lines):
    assert pdf.extract(pdfs.paper_pdf(title_lines=title_lines)).title == " ".join(title_lines)


def test_a_title_set_in_two_fonts_reads_as_plain_text():
    x = LEFT + width("Retrieval ", 20, "hebo")
    data = layout_pdf(first_page(
        Text(90, "Retrieval ", 20, "hebo"), Text(90, "Augmented", 20, "hebi", x=x),
        Text(90, " Generation", 20, "hebo", x=x + width("Augmented", 20, "hebi")),
        Text(130, AUTHORS_LINE, 11)))

    assert pdf.extract(data).title == "Retrieval Augmented Generation"


@pytest.mark.parametrize("other", [
    Text(560, "RETRIEVER", 28, "hebo"),  # larger, but in a figure lower on the page
    Text(60, "ACL", 30, "hebo"),  # a venue logo: larger, but too short for a title
    Text(500, "arXiv:1706.03762v7 [cs.CL] 2 Aug 2023", 24, "tiro", x=30, rotate=90),  # arXiv's margin stamp
    Text(300, "Under review: please do not cite", 20, "hebo"),  # the title's size again, further down
], ids=["figure label", "logo", "arXiv stamp", "banner"])
def test_the_title_is_the_largest_text_at_the_top_of_page_1(other):
    data = layout_pdf(first_page(Text(110, TITLE, 20, "hebo"), Text(150, AUTHORS_LINE, 11), other))

    assert pdf.extract(data).title == TITLE


@pytest.mark.parametrize("largest", ["BERT", "Retrieval augmented generation " * 11],
                         ids=["too short", "too long"])
def test_text_too_short_or_too_long_for_a_title_is_not_taken_as_one(largest):
    lines = [Text(90 + 24 * n, largest[i:i + 40], 20, "hebo") for n, i in enumerate(range(0, len(largest), 40))]

    assert pdf.extract(layout_pdf(first_page(*lines))).title is None


# Authors are read from the lines below the title, up to the abstract.

@pytest.mark.parametrize("lines", [
    # A one-line title, directly followed by the authors.
    [Text(90, TITLE, 20, "hebo"), Text(130, AUTHORS_LINE, 11)],
    # Each author on a line of their own, with their affiliation below.
    [Text(90, TITLE, 20, "hebo"), Text(130, "Alice Smith", 11), Text(144, "Example University, Boston", 10),
     Text(162, "Bob Jones", 11), Text(176, "Institute of Technology", 10), Text(194, "Carol White", 11),
     Text(208, "Third College", 10)],
    # A line of email addresses that also names the authors.
    [Text(90, TITLE, 20, "hebo"), Text(130, AUTHORS_LINE, 11),
     Text(146, "Alice Smith (alice@example.edu), Bob Jones (bob@example.edu)", 10)],
    # An empty line (spaces only) inside the author block.
    [Text(90, TITLE, 20, "hebo"), Text(130, "Alice Smith, Bob Jones", 11), Text(143, "   ", 11),
     Text(156, "Carol White", 11)],
], ids=["one-line title", "affiliation lines", "email line", "blank line"])
def test_authors_are_read_from_below_the_title(lines):
    assert pdf.extract(layout_pdf(first_page(*lines))).authors == SAMPLE_AUTHORS


def test_the_author_search_stops_at_an_abstract_heading_in_capitals():
    # ACM style: "ABSTRACT" in capitals, and a line of capitalized keywords below the abstract.
    data = layout_pdf([
        Text(90, TITLE, 20, "hebo"), Text(130, AUTHORS_LINE, 11), Text(170, "ABSTRACT", 12, "hebo"),
        *wrapped(188, SAMPLE_ABSTRACT), Text(240, "KEYWORDS: Retrieval Augmentation, Large Language Models", 10),
        *wrapped(300, FILLER)])

    assert pdf.extract(data).authors == SAMPLE_AUTHORS


def test_without_a_title_no_authors_are_guessed():
    # Nothing large at the top of page 1 (reading notes, say): no title, so no author line either.
    data = pdfs.unstructured_pdf([
        "Reading notes on retrieval augmented generation for the related work chapter of my thesis, "
        "with the main claims of each paper.", "Alice Smith, Bob Jones", FILLER])

    extracted = pdf.extract(data)

    assert (extracted.title, extracted.authors) == (None, [])


def test_a_placeholder_author_in_pdf_properties_is_ignored():
    assert pdf.extract(pdfs.paper_pdf(metadata={"author": "me"})).authors == SAMPLE_AUTHORS


def test_a_picture_on_the_first_page_does_not_stop_the_metadata():
    data = layout_pdf(first_page(Text(110, TITLE, 20, "hebo"), Text(150, AUTHORS_LINE, 11)),
                      images={0: pymupdf.Rect(420, 30, 520, 80)})  # a logo

    extracted = pdf.extract(data)

    assert (extracted.title, extracted.authors, extracted.abstract) == (TITLE, SAMPLE_AUTHORS, SAMPLE_ABSTRACT)


@pytest.mark.parametrize(("line", "names"), [
    ("Alice Smith, Bob Jones and Carol White", ["Alice Smith", "Bob Jones", "Carol White"]),
    ("Alice Smith1,2, Bob Jones∗ & Carol White†", ["Alice Smith", "Bob Jones", "Carol White"]),
    ("Ashish Vaswani    Noam Shazeer    Niki Parmar", ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]),
    ("Kaiming He · Xiangyu Zhang", ["Kaiming He", "Xiangyu Zhang"]),
    ("Alice Smith, Bob Jones.", ["Alice Smith", "Bob Jones"]),  # punctuation at the end
    ("Juan Carlos De La Fuente, Ross B Girshick", ["Juan Carlos De La Fuente", "Ross B Girshick"]),
    ("we propose a method", []),  # not capitalized names
    ("Deep Learning For Natural Language Processing", []),  # too many words for a name
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


def test_a_paper_from_this_year_gets_this_year():
    this_year = date.today().year

    cited = "as in (Vaswani et al., 2017) and (Devlin et al., 2017)"
    assert pdf._guess_year(f"Proceedings of ACL {this_year}\n{cited}", {}) == this_year  # next to a venue
    assert pdf._guess_year(f"Submitted in March {this_year}.", {}) == this_year  # anywhere on page 1
    assert pdf._guess_year("No year here.", {"creationDate": f"D:{this_year}0305120000Z"}) == this_year


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


@pytest.mark.parametrize("after", ["", "\n1 Introduction\nThe introduction."], ids=["nothing after it", "an introduction"])
def test_an_abstract_that_runs_on_is_cut_to_its_first_3000_characters(after):
    body = "We study retrieval augmented generation in depth and report what we found. " * 80  # 6,000 characters

    abstract = pdf._guess_abstract(f"Abstract\n{body}{after}")

    assert abstract.startswith("We study retrieval augmented generation in depth")
    assert 2900 < len(abstract) <= 3000


def test_an_abstract_that_continues_on_page_2_is_read_across_the_page_break():
    lines = wrapped(0, SAMPLE_ABSTRACT)
    data = layout_pdf(
        [Text(90, TITLE, 20, "hebo"), Text(130, AUTHORS_LINE, 11), *wrapped(200, FILLER), *wrapped(300, FILLER),
         Text(712, "Abstract", 12, "hebo"), *[Text(730 + 13.5 * n, line.text) for n, line in enumerate(lines[:2])]],
        [*[Text(90 + 13.5 * n, line.text) for n, line in enumerate(lines[2:])], Text(140, "1 Introduction", 12, "hebo"),
         *wrapped(158, FILLER)])

    assert pdf.extract(data).abstract == SAMPLE_ABSTRACT


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
    (pdfs.empty_pdf(), "The PDF has no pages."),
    (pdfs.blank_pdf(), "No text could be extracted. The PDF may be a scanned image."),
])
def test_unusable_pdfs_raise_a_readable_error(data, message):
    with pytest.raises(pdf.PdfError) as raised:
        pdf.extract(data)

    assert str(raised.value) == message


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
    with pytest.raises(pdf.PdfError) as raised:
        pdf.extract_outline(b"not a pdf")

    assert str(raised.value) == "The file could not be read as a PDF."


def titles_of(data: bytes) -> list[str]:
    return [entry.title for entry in pdf.extract_outline(data)]


# A numbered list in running text: it looks like numbered headings, but in the body's own font.
STEPS = ["1 Retrieve the top passages for each question", "2 Rerank them with a cross-encoder",
         "3 Generate the answer from the best passage"]


def test_headings_in_a_regular_font_a_size_larger_than_the_text_are_found():
    # ACL-like sizes: 11 pt text, 12 pt headings, none of it bold.
    data = layout_pdf(
        [Text(90, TITLE, 17), Text(130, AUTHORS_LINE, 11), Text(170, "Abstract", 12),
         *wrapped(188, SAMPLE_ABSTRACT, 11), Text(260, "1 Introduction", 12),
         *wrapped(278, "Large language models often state facts that are wrong. We add retrieval in three steps:", 11),
         *[Text(310 + 15 * n, step, 11) for n, step in enumerate(STEPS)],
         Text(380, "2 Method", 12), *wrapped(398, FILLER, 11)],
        [Text(90, "3 Results", 12), *wrapped(108, FILLER, 11), Text(200, "4 Conclusion and Future Work", 12),
         *wrapped(218, "Retrieval keeps language models factual, and it is simple to add to any of them.", 11),
         Text(250, "Thanks.", 11)])  # the paper ends on a short line

    assert [(e.title, e.page) for e in pdf.extract_outline(data)] == [
        ("Abstract", 1), ("1 Introduction", 1), ("2 Method", 1), ("3 Results", 2), ("4 Conclusion and Future Work", 2)]


@pytest.mark.parametrize("font", ["hebo", "tiro"], ids=["bold", "medium weight"])
def test_headings_in_a_heavier_font_at_the_text_size_are_found(font):
    # ACL subsection style: the heading has the text's size, only its weight stands out.
    # "tiro" is renamed to a medium-weight font, which PDF readers do not flag as bold.
    data = layout_pdf(
        [Text(90, "1 Introduction", 11, font), *wrapped(108, FILLER, 11), *[Text(170 + 15 * n, step, 11) for n, step in enumerate(STEPS)],
         Text(240, "2 Related Work", 11, font), *wrapped(258, FILLER, 11), Text(330, "3 Method", 11, font),
         *wrapped(348, FILLER, 11), Text(420, "References", 11, font), Text(438, "[1] A. Author. 2020.", 11)],
        font_names={"Times-Roman": "Inter-Medium"})

    assert titles_of(data) == ["1 Introduction", "2 Related Work", "3 Method", "References"]


def test_a_paper_with_named_sections_and_a_numbered_list_keeps_its_named_sections():
    # Common in the life sciences: unnumbered sections, and numbered steps in the text.
    data = layout_pdf(
        [Text(90, "Introduction", 12, "hebo"), *wrapped(108, FILLER), Text(180, "Methods", 12, "hebo"),
         *wrapped(198, "The protocol has three steps:"), *[Text(225 + 14 * n, step) for n, step in enumerate(STEPS)]],
        [Text(90, "Results", 12, "hebo"), *wrapped(108, FILLER), Text(180, "Discussion", 12, "hebo"),
         *wrapped(198, FILLER), Text(270, "References", 12, "hebo"), Text(288, "[1] A. Author. 2020.")])

    assert titles_of(data) == ["Introduction", "Methods", "Results", "Discussion", "References"]


def test_section_numbers_set_apart_from_their_headings_are_joined_to_them():
    # Some templates (e.g. ACL) set "2" and "Method" as two pieces of text side by side.
    def heading(y: float, number: str, title: str) -> list[Text]:
        return [Text(y, number, 12, "hebo"), Text(y, title, 12, "hebo", x=LEFT + width(number, 12, "hebo") + 12)]

    data = layout_pdf([
        Text(90, TITLE, 20, "hebo"), Text(130, AUTHORS_LINE, 11), Text(170, "Abstract", 12, "hebo"),
        *wrapped(188, SAMPLE_ABSTRACT), *heading(260, "1", "Introduction"),
        Text(278, "Large language models often state facts that are wrong, and retrieval", x=LEFT + 15),  # indented
        *wrapped(291.5, FILLER), *heading(360, "2", "Method"), *heading(376, "2.1", "Retriever"),
        *wrapped(394, FILLER), *heading(470, "3.", "Results"), *wrapped(488, FILLER)])

    assert [(e.level, e.title) for e in pdf.extract_outline(data)] == [
        (1, "Abstract"), (1, "1 Introduction"), (1, "2 Method"), (2, "2.1 Retriever"), (1, "3 Results")]


@pytest.mark.parametrize(("next_line", "expected"), [
    (Text(315, "Knowledge-Intensive Tasks", 12, "hebo"),
     ["3 Retrieval Augmented Generation for Knowledge-Intensive Tasks"]),  # it continues the heading
    (Text(315, "Datasets and metrics", 11, "hebo"), ["3 Experiments"]),  # a paragraph heading, smaller
    (Text(315, "Datasets and metrics", 12), ["3 Experiments"]),  # not bold
    (Text(315, "3.1 Setup", 12, "hebo"), ["3 Experiments", "3.1 Setup"]),  # the next heading
    (Text(315, "Results", 12, "hebo"), ["3 Experiments", "Results"]),  # the next heading, unnumbered
    (Text(315, "We report the mean of three runs.", 12, "hebo"), ["3 Experiments"]),  # a sentence
    (Text(334, "Datasets and metrics", 12, "hebo"), ["3 Experiments"]),  # too far below
], ids=["continuation", "smaller", "regular weight", "numbered heading", "named heading", "sentence", "far below"])
def test_a_heading_takes_the_next_line_only_if_it_continues_the_heading(next_line, expected):
    heading = "3 Retrieval Augmented Generation for" if next_line.text.startswith("Knowledge") else "3 Experiments"
    data = layout_pdf([Text(90, TITLE, 20, "hebo"), *wrapped(130, FILLER), Text(300, heading, 12, "hebo"), next_line,
                       *wrapped(370, FILLER)])

    assert titles_of(data) == expected


def test_a_heading_on_the_last_line_of_the_pdf_is_listed():
    data = layout_pdf([Text(90, "1 Introduction", 12, "hebo"), *wrapped(108, FILLER)],
                      [*wrapped(90, FILLER), Text(200, "2 Appendix Tables", 12, "hebo")])

    assert titles_of(data) == ["1 Introduction", "2 Appendix Tables"]


def test_named_headings_in_capitals_are_listed_in_title_case_and_others_as_written():
    data = layout_pdf([Text(90, "ABSTRACT", 12, "hebo"), *wrapped(108, FILLER), Text(180, "INTRODUCTION", 12, "hebo"),
                       *wrapped(198, FILLER), Text(270, "Related work", 12, "hebo"), *wrapped(288, FILLER),
                       Text(360, "CONCLUSIONS", 12, "hebo"), *wrapped(378, FILLER)])

    assert titles_of(data) == ["Abstract", "Introduction", "Related work", "Conclusions"]


def test_in_a_paper_with_numbered_sections_an_unnumbered_results_label_is_not_a_section():
    # Three numbered sections make a numbered paper; a bold "Results" there labels a table.
    data = layout_pdf([Text(90, "1 Introduction", 12, "hebo"), *wrapped(108, FILLER), Text(180, "2 Method", 12, "hebo"),
                       *wrapped(198, FILLER), Text(270, "Results", 10, "hebo"), Text(285, "Model  Accuracy"),
                       Text(330, "3 Conclusion", 12, "hebo"), *wrapped(348, FILLER)])

    assert titles_of(data) == ["1 Introduction", "2 Method", "3 Conclusion"]


def test_numbered_lines_that_are_not_sections_are_left_out():
    data = layout_pdf([
        Text(90, "1 Introduction", 12, "hebo"), *wrapped(108, FILLER), Text(180, "2 RAG", 12, "hebo"),  # an acronym
        *wrapped(198, FILLER),
        Text(260, "24 Heads", 10, "hebo"), Text(274, "3 GB", 10, "hebo"),  # table cells: too large a number, no words
        *[Text(300 + 14 * n, item, 10, "hebo") for n, item in enumerate([  # a bold list, written as sentences
            "1 We propose a new retriever.", "2 We show that it helps,", "3 We release the code;", "4 We list open problems:"])],
        Text(380, "3 Results", 12, "hebo"), *wrapped(398, FILLER)])

    assert titles_of(data) == ["1 Introduction", "2 RAG", "3 Results"]


def test_a_running_header_that_repeats_a_heading_is_listed_once():
    data = layout_pdf(
        [Text(90, "1 Introduction", 12, "hebo"), *wrapped(108, FILLER)],
        [Text(40, "2 Method", 9, "hebo"), Text(90, "2 Method", 12, "hebo"), *wrapped(108, FILLER)],
        [Text(40, "2 Method", 9, "hebo"), *wrapped(90, FILLER), Text(200, "3 Results", 12, "hebo"), *wrapped(218, FILLER)])

    assert titles_of(data) == ["1 Introduction", "2 Method", "3 Results"]


@pytest.mark.parametrize("obstacle", ["rotated label", "picture", "blank line", "two fonts"])
def test_headings_are_found_next_to_other_page_content(obstacle):
    first = [Text(90, "1 Method", 12, "hebo"), *wrapped(108, FILLER)]
    second = [Text(90, "2 Results", 12, "hebo"), *wrapped(108, FILLER)]
    if obstacle == "rotated label":  # a figure's axis label on page 1, bold and turned on its side
        first.append(Text(500, "Results", 12, "hebo", x=60, rotate=90))
    if obstacle == "blank line":  # a line of spaces just above the heading, in the same block
        second[:1] = [Text(78, "   "), Text(90, "2 Results", 12, "hebo")]
    if obstacle == "two fonts":  # the heading in two fonts: bold, and bold italic
        second[:1] = [Text(90, "2 ", 12, "hebo"), Text(90, "Results", 12, "hebi", x=LEFT + width("2 ", 12, "hebo"))]
    data = layout_pdf(first, second, images={1: pymupdf.Rect(300, 400, 400, 480)} if obstacle == "picture" else None)

    assert [(e.title, e.page) for e in pdf.extract_outline(data)] == [("1 Method", 1), ("2 Results", 2)]
    # Section names from the model are found at their headings too.
    assert [spot[0] for spot in pdf.locate_headings(data, ["Method", "Results"])] == [1, 2]


def test_the_outline_of_headings_is_bounded():
    headings = [f"{section}.{sub} Part" if sub else f"{section} Part" for section in range(1, 21) for sub in range(8)]
    pages = [[Text(60 + 20 * n, heading, 12, "hebo") for n, heading in enumerate(headings[i:i + 32])]
             for i in range(0, len(headings), 32)]

    entries = pdf.extract_outline(layout_pdf(*pages))

    assert len(headings) > pdf.MAX_OUTLINE_ENTRIES
    assert [e.title for e in entries] == headings[:pdf.MAX_OUTLINE_ENTRIES]


def test_a_pdf_whose_text_is_all_turned_on_its_side_has_no_outline():
    # E.g. landscape pages saved rotated: no line reads left to right.
    data = layout_pdf([Text(700 - 40 * n, f"{n} Introduction to the topic", 12, "hebo", x=60 + 30 * n, rotate=90)
                       for n in range(1, 4)])

    assert pdf.extract_outline(data) == []
    assert pdf.locate_headings(data, ["Introduction"]) == [None]


def test_bookmarks_point_where_they_lead_on_their_page():
    doc = pymupdf.open()
    for page_width, page_height in [(612, 792), (612, 792), (792, 612)]:  # page 3 is landscape
        doc.new_page(width=page_width, height=page_height)
    doc.set_toc([
        [1, "Introduction", 1, {"kind": pymupdf.LINK_GOTO, "page": 0, "to": pymupdf.Point(72, 300)}],
        [1, "Method", 2],  # becomes a named destination below, as LaTeX (hyperref) writes them
        [1, "Results", 2],  # also named, but to the whole page (/Fit): its top
        [1, "Appendix", 3, {"kind": pymupdf.LINK_GOTO, "page": 2, "to": pymupdf.Point(0, 200)}],
        [1, "Notes", 1, {"kind": pymupdf.LINK_GOTO, "page": 0, "to": pymupdf.Point(72, 900)}],  # past the foot
    ])
    method, results = [entry[3]["xref"] for entry in doc.get_toc(simple=False)][1:3]
    # Named destinations are given in PDF coordinates, counted from the bottom of the page.
    doc.xref_set_key(doc.pdf_catalog(), "Dests",
                     f"<</sec.method [{doc[1].xref} 0 R /XYZ 72 302 0] /sec.results [{doc[1].xref} 0 R /Fit]>>")
    doc.xref_set_key(method, "Dest", "/sec.method")
    doc.xref_set_key(results, "Dest", "/sec.results")

    entries = pdf.extract_outline(doc.tobytes())

    assert [(e.title, e.page) for e in entries] == [
        ("Introduction", 1), ("Method", 2), ("Results", 2), ("Appendix", 3), ("Notes", 1)]
    assert [e.top for e in entries] == [
        pytest.approx(300 / 792, abs=1e-3), pytest.approx((792 - 302) / 792, abs=1e-3), 0.0,
        pytest.approx(200 / 612, abs=1e-3), 1.0]


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


def test_a_heading_in_a_regular_font_beats_an_earlier_sentence_that_starts_with_the_name():
    # 11 pt text and 12 pt headings, none bold: the heading stands out by its size alone.
    data = layout_pdf(
        [Text(90, TITLE, 17), Text(130, "1 Introduction", 12), *wrapped(148, FILLER, 11),
         Text(220, "Results improve by eleven points over the strongest baseline in every setting.", 11),
         *wrapped(235, FILLER, 11)],
        [Text(300, "4 Results and Discussion", 12), *wrapped(318, FILLER, 11)])

    [(page, top)] = pdf.locate_headings(data, ["Results"])

    assert page == 2 and top == pytest.approx(heading_top(data, "4 Results and Discussion"), abs=0.01)


def test_a_section_named_with_a_three_letter_acronym_is_found():
    data = layout_pdf([Text(90, "1 Introduction", 12, "hebo"), *wrapped(108, FILLER)],
                      [Text(300, "2 RAG", 12, "hebo"), *wrapped(318, FILLER)])

    assert [spot[0] if spot else None for spot in pdf.locate_headings(data, ["RAG"])] == [2]


def heading_top(data: bytes, text: str) -> float:
    """Where `text` is drawn on its page (0 = top), found independently with PyMuPDF."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        page, rect = next((page, rects[0]) for page in doc if (rects := page.search_for(text)))
        return rect.y0 / page.rect.height
