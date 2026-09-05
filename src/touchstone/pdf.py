# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""A small PDF writer, so a report can be handed to somebody who reads documents.

No dependency. The README's claim is three runtime dependencies and CI installs the package
with the network off, and a PDF library that wants cairo and pango on the host would cost
both. A typeset page of text, rules and tables needs the base fourteen fonts and a content
stream, which is a few hundred lines and stays inside the same promise.

The bytes are deterministic. There is no creation date and no document identifier, so the
same report over the same bundle hashes to the same value and can be sealed into the bundle
it describes. A PDF carrying a timestamp could not be.

Widths are the Helvetica and Helvetica-Bold AFM tables, read from the metrically compatible
URW faces that ship with matplotlib rather than typed from memory. Courier is monospaced at
600 for every glyph, which is its whole definition.
"""

import zlib
from dataclasses import dataclass, field

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
"""A4 at 72 points to the inch, rounded to whole points to keep the arithmetic exact."""

REGULAR = "F1"
BOLD = "F2"
MONO = "F3"

# fmt: off
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 222, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    222, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)

_HELVETICA_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 278, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    278, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)
# fmt: on

_FIRST = 32
_FALLBACK = "?"
"""Anything outside printable ASCII becomes this. The report is written in ASCII and a
silent substitution is better than a page that renders a different character than the one
the bundle holds."""


def width(text: str, font: str, size: float) -> float:
    """The set width of a string, in points."""
    if font == MONO:
        return len(text) * 600 * size / 1000
    table = _HELVETICA_BOLD if font == BOLD else _HELVETICA
    total = 0
    for character in text:
        code = ord(character)
        total += table[code - _FIRST] if _FIRST <= code <= 126 else table[ord(_FALLBACK) - _FIRST]
    return total * size / 1000


def wrap(text: str, font: str, size: float, limit: float) -> list[str]:
    """Break on spaces to fit `limit` points. A single word longer than the column is left
    to overrun rather than hyphenated, because the words that do it here are hashes and a
    hash broken across two lines cannot be copied."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and width(candidate, font, size) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _escape(text: str) -> str:
    safe = "".join(character if 32 <= ord(character) <= 126 else _FALLBACK for character in text)
    return safe.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


@dataclass
class Page:
    """One page's content stream, built up as operators."""

    operators: list[str] = field(default_factory=list)

    def text(
        self,
        x: float,
        y: float,
        body: str,
        font: str,
        size: float,
        grey: float = 0.0,
        tracking: float = 0.0,
    ) -> None:
        self.operators.append(
            f"BT {grey:.3f} g /{font} {size:g} Tf {tracking:g} Tc "
            f"{x:.2f} {y:.2f} Td ({_escape(body)}) Tj ET"
        )

    def rule(
        self, x: float, y: float, length: float, grey: float = 0.8, thickness: float = 0.5
    ) -> None:
        self.operators.append(
            f"{grey:.3f} G {thickness:g} w {x:.2f} {y:.2f} m {x + length:.2f} {y:.2f} l S"
        )

    def bar(self, x: float, y: float, w: float, h: float, grey: float) -> None:
        """A filled rectangle. Used for the status marker beside a finding."""
        self.operators.append(f"{grey:.3f} g {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def stream(self) -> bytes:
        return "\n".join(self.operators).encode("ascii")


def render(pages: list[Page]) -> bytes:
    """The pages as a PDF file. Objects are numbered in the order they are written, and the
    cross reference table is built from the byte offsets as they land."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_ids = {
        REGULAR: add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        ),
        BOLD: add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        ),
        MONO: add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
        ),
    }
    resources = (
        "<< /Font << "
        + " ".join(f"/{name} {number} 0 R" for name, number in font_ids.items())
        + " >> >>"
    )

    # Three fonts are written, then a content stream and a page object each, then the
    # tree. Pages have to name their parent before it exists, so the number is predicted
    # here and the assert below is what catches a miscount.
    pages_id = len(objects) + 2 * len(pages) + 1
    page_ids = []
    for page in pages:
        # Flate rather than raw, because a report is mostly repeated operators and the
        # saving is large. The filter is the only one every reader has had since 1.2.
        body = zlib.compress(page.stream(), 9)
        content = add(
            b"<< /Length " + str(len(body)).encode() + b" /Filter /FlateDecode >>\n"
            b"stream\n" + body + b"\nendstream"
        )
        page_ids.append(
            add(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources {resources} /Contents {content} 0 R >>".encode()
            )
        )

    kids = " ".join(f"{number} 0 R" for number in page_ids)
    tree = add(f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode())
    assert tree == pages_id, "the page tree landed at an object number the pages do not name"
    catalog = add(f"<< /Type /Catalog /Pages {tree} 0 R >>".encode())

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    # No /ID and no /Info. Both would carry something that changes between two runs over
    # the same bundle, and this file is meant to hash the same way twice.
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\n".encode()
    out += f"startxref\n{start}\n%%EOF\n".encode()
    return bytes(out)
