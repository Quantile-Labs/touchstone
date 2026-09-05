"""The PDF writer, on its own.

It exists so a report can be handed to somebody who reads documents, without a dependency
that wants cairo and pango on the host and would cost the offline install CI tests on every
change. What has to hold is that the file parses, that the bytes are the same twice, and
that a line of text fits the column it was measured for.
"""

import re
import zlib

from touchstone import pdf


def page_with(text: str) -> pdf.Page:
    page = pdf.Page()
    page.text(56, 700, text, pdf.REGULAR, 9)
    return page


def streams(raw: bytes) -> str:
    found = re.findall(rb"stream\n(.*?)\nendstream", raw, re.S)
    return "\n".join(zlib.decompress(body).decode("latin-1") for body in found)


def test_the_file_parses_as_a_pdf():
    raw = pdf.render([page_with("hello")])

    assert raw.startswith(b"%PDF-1.4")
    assert raw.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in raw
    assert b"/Type /Pages" in raw


def test_the_cross_reference_table_points_at_every_object():
    """A reader that cannot resolve an object shows a blank page and says nothing useful,
    so the offsets are checked against what is actually at them."""
    raw = pdf.render([page_with("hello"), page_with("again")])

    start = int(re.search(rb"startxref\n(\d+)\n", raw).group(1))
    table = raw[start:].split(b"\n")
    assert table[0] == b"xref"
    count = int(table[1].split()[1])

    for number, line in enumerate(table[3 : 2 + count], start=1):
        offset = int(line.split()[0])
        assert raw[offset:].startswith(f"{number} 0 obj".encode()), f"object {number}"


def test_two_renders_of_the_same_pages_are_the_same_bytes():
    """No creation date and no document identifier, so a statement can be hashed."""
    assert pdf.render([page_with("hello")]) == pdf.render([page_with("hello")])


def test_every_page_reaches_the_page_tree():
    raw = pdf.render([page_with("one"), page_with("two"), page_with("three")])
    tree = re.search(rb"/Type /Pages /Count (\d+) /Kids \[(.*?)\]", raw)

    assert int(tree.group(1)) == 3
    assert len(tree.group(2).split(b" 0 R")) - 1 == 3


def test_a_wrapped_line_fits_the_column_it_was_measured_for():
    """Wrapping runs off the Helvetica width tables. A line that overruns means the table
    is wrong, and it shows up as text running past the edge of the page."""
    prose = "the quick brown fox jumps over the lazy dog " * 8
    for font in (pdf.REGULAR, pdf.BOLD, pdf.MONO):
        for line in pdf.wrap(prose, font, 9, 300):
            assert pdf.width(line, font, 9) <= 300


def test_a_word_longer_than_the_column_is_left_whole():
    """The words that do this are hashes, and a hash broken over two lines cannot be
    copied out of the document by the person checking it."""
    digest = "a" * 64
    assert pdf.wrap(digest, pdf.MONO, 7.5, 100) == [digest]


def test_the_widths_are_the_real_metrics_and_not_a_guess():
    """Three glyphs whose Helvetica widths differ from each other and from the average.
    A table filled with one number would pass every other test in this file."""
    assert pdf.width("i", pdf.REGULAR, 1000) == 222
    assert pdf.width("W", pdf.REGULAR, 1000) == 944
    assert pdf.width(" ", pdf.REGULAR, 1000) == 278
    assert pdf.width("i", pdf.BOLD, 1000) == 278
    assert pdf.width("iW ", pdf.MONO, 1000) == 1800


def test_parentheses_and_backslashes_do_not_break_the_stream():
    """Unescaped, either one ends the string early and the rest of the page becomes
    operators. A pack id is free text and can hold both."""
    raw = pdf.render([page_with(r"a (b) \c")])
    assert r"(a \(b\) \\c) Tj" in streams(raw)


def test_a_character_outside_ascii_is_replaced_rather_than_mangled():
    """The base fourteen fonts are single byte encoded. Writing a wider character raw sets
    a different glyph than the bundle holds, which is worse than admitting the gap."""
    assert "(?) Tj" in streams(pdf.render([page_with("—")]))
