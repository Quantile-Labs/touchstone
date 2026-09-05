# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

"""The conformance statement, set as a document.

One typeface, three weights of grey and a hairline rule. A report that somebody has to
carry into a procurement conversation is read in a hurry by people who are not going to
open `estimates.json`, and the thing that makes it useful is that every number on the page
came out of a file they can open if they want to.

Nothing here computes. The figures are read from the bundle and set; the arithmetic
happened in `estimate` and `grade`, where it is tested.
"""

from touchstone.contracts.estimates import Estimates
from touchstone.contracts.report import Report
from touchstone.contracts.scorecard import Scorecard
from touchstone.pdf import BOLD, MONO, PAGE_HEIGHT, PAGE_WIDTH, REGULAR, Page, render, width, wrap

LEFT = 56.0
RIGHT = PAGE_WIDTH - LEFT
TOP = PAGE_HEIGHT - 64.0
BOTTOM = 72.0
COLUMN = RIGHT - LEFT

INK = 0.0
MUTED = 0.42
FAINT = 0.62
HAIRLINE = 0.86

INDENT = 54.0
"""Width of the practice reference column. Every requirement and detail line starts after
it, so the references form a margin the eye can run down."""


class Cursor:
    """A page and a y position, with the page break in one place."""

    def __init__(self) -> None:
        self.pages = [Page()]
        self.y = TOP

    @property
    def page(self) -> Page:
        return self.pages[-1]

    def need(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.pages.append(Page())
            self.y = TOP

    def down(self, amount: float) -> None:
        self.y -= amount

    def rule(self, grey: float = HAIRLINE, x: float = LEFT, length: float = COLUMN) -> None:
        self.page.rule(x, self.y, length, grey)


def _label(cursor: Cursor, text: str, x: float, grey: float = FAINT) -> None:
    """A column head. Uppercase, tracked, small, and never bold, because a page of bold
    labels is a page with no hierarchy."""
    cursor.page.text(x, cursor.y, text.upper(), REGULAR, 6.5, grey, tracking=1.1)


def _right(
    page: Page,
    text: str,
    y: float,
    font: str,
    size: float,
    grey: float = INK,
    edge: float = RIGHT,
    tracking: float = 0.0,
) -> None:
    page.text(
        edge - width(text, font, size) - tracking * len(text), y, text, font, size, grey, tracking
    )


def _paragraph(
    cursor: Cursor,
    text: str,
    x: float,
    size: float,
    grey: float,
    font: str = REGULAR,
    leading: float = 1.35,
) -> None:
    limit = RIGHT - x
    for line in wrap(text, font, size, limit):
        cursor.need(size * leading)
        cursor.page.text(x, cursor.y, line, font, size, grey)
        cursor.down(size * leading)


def _heading(cursor: Cursor, text: str) -> None:
    cursor.need(46)
    cursor.down(16)
    cursor.page.text(LEFT, cursor.y, text, BOLD, 10.5, INK)
    cursor.down(7)
    cursor.rule(grey=0.55)
    cursor.down(15)


def _masthead(cursor: Cursor, report: Report) -> None:
    page = cursor.page
    page.text(LEFT, cursor.y, "CONFORMANCE STATEMENT", REGULAR, 7, MUTED, tracking=1.6)
    cursor.down(26)

    name = report.bundle.rstrip("/").rsplit("/", 1)[-1]
    page.text(LEFT, cursor.y, name, BOLD, 21, INK)
    cursor.down(16)
    page.text(LEFT, cursor.y, report.source, REGULAR, 9, MUTED)
    cursor.down(18)
    cursor.rule(grey=0.35, length=COLUMN)
    cursor.down(20)

    third = COLUMN / 3
    fields = [
        ("sealed", report.sealed_utc or "not sealed"),
        ("access tier", report.access_tier or "not recorded"),
        ("hashes", {True: "verified", False: "failed", None: "not sealed"}[report.verified]),
    ]
    for index, (label, _) in enumerate(fields):
        _label(cursor, label, LEFT + index * third)
    cursor.down(12)
    for index, (_, value) in enumerate(fields):
        cursor.page.text(LEFT + index * third, cursor.y, value, REGULAR, 9, INK)
    cursor.down(20)

    for label, digest in [
        ("bundle sha-256", report.bundle_sha256),
        ("plan sha-256", report.plan_sha256),
    ]:
        _label(cursor, label, LEFT)
        cursor.page.text(LEFT + 92, cursor.y, digest or "not recorded", MONO, 7.5, INK)
        cursor.down(14)

    cursor.down(4)
    counts = (
        f"{len(report.findings)} practice items. {report.met} met, {report.unmet} not met, "
        f"{sum(1 for f in report.findings if f.status == 'not applicable')} not applicable."
    )
    cursor.page.text(LEFT, cursor.y, counts, REGULAR, 9, INK)
    cursor.down(6)


def _findings(cursor: Cursor, report: Report) -> None:
    _heading(cursor, "Findings")
    for finding in report.findings:
        requirement = wrap(finding.requirement, BOLD, 9.5, RIGHT - INDENT - LEFT - 70)
        detail = wrap(finding.detail, REGULAR, 8.5, COLUMN - INDENT)
        cursor.need(14 * len(requirement) + 11.5 * len(detail) + 26)

        cursor.page.text(
            LEFT,
            cursor.y,
            finding.practice or "added",
            REGULAR,
            8,
            MUTED if finding.practice else FAINT,
        )
        _right(
            cursor.page,
            finding.status.upper(),
            cursor.y,
            REGULAR,
            6.5,
            INK if finding.status == "not met" else MUTED,
            tracking=1.1,
        )
        for line in requirement:
            cursor.page.text(LEFT + INDENT, cursor.y, line, BOLD, 9.5, INK)
            cursor.down(13)
        cursor.down(1)
        for line in detail:
            cursor.page.text(LEFT + INDENT, cursor.y, line, REGULAR, 8.5, MUTED)
            cursor.down(11.5)
        if finding.evidence:
            cursor.page.text(LEFT + INDENT, cursor.y, "  ".join(finding.evidence), MONO, 7, FAINT)
            cursor.down(12)
        cursor.down(4)
        cursor.rule()
        cursor.down(14)


def _fit(text: str, font: str, size: float, limit: float) -> str:
    """Trim a cell to its column. A metric name long enough to run into the next column
    would put two values on one line and make the row unreadable."""
    if width(text, font, size) <= limit:
        return text
    while text and width(text + "...", font, size) > limit:
        text = text[:-1]
    return text + "..."


def _interval(low: float, high: float, point: float | None) -> tuple[str, str]:
    if point is None:
        return "no items", ""
    return f"{point * 100:.1f}%", f"{low * 100:.1f} to {high * 100:.1f}"


def _measurements(cursor: Cursor, estimates: Estimates | None) -> None:
    if estimates is None or not estimates.estimates:
        return
    _heading(cursor, "Measurements")

    columns = (LEFT, LEFT + 132, LEFT + 264, LEFT + 316, LEFT + 380)
    for x, name in zip(columns, ("outcome", "stratum", "n", "rate", "95% interval"), strict=True):
        if name in {"n", "rate", "95% interval"}:
            _right(
                cursor.page,
                name.upper(),
                cursor.y,
                REGULAR,
                6.5,
                FAINT,
                edge=x + (48 if name == "n" else 60 if name == "rate" else 103),
                tracking=1.1,
            )
        else:
            _label(cursor, name, x)
    cursor.down(6)
    cursor.rule(grey=0.55)
    cursor.down(13)

    for estimate in estimates.estimates:
        cursor.need(22)
        rate, span = _interval(estimate.low, estimate.high, estimate.point)
        cell = ", ".join(f"{key}={value}" for key, value in sorted(estimate.stratum.items()))
        cursor.page.text(
            columns[0], cursor.y, _fit(estimate.metric, REGULAR, 8.5, 126), REGULAR, 8.5, INK
        )
        cursor.page.text(
            columns[1],
            cursor.y,
            _fit(cell or "whole sample", REGULAR, 8.5, 126),
            REGULAR,
            8.5,
            MUTED,
        )
        _right(cursor.page, str(estimate.n), cursor.y, REGULAR, 8.5, MUTED, edge=columns[2] + 48)
        _right(cursor.page, rate, cursor.y, REGULAR, 8.5, INK, edge=columns[3] + 60)
        _right(cursor.page, span, cursor.y, REGULAR, 8.5, MUTED, edge=columns[4] + 103)
        cursor.down(9)
        cursor.rule(grey=0.92)
        cursor.down(12)

    cursor.down(2)
    methods = sorted({estimate.estimator for estimate in estimates.estimates})
    _paragraph(
        cursor,
        f"Estimators: {', '.join(methods)}. Every interval is read from "
        f"estimates.json with the denominator it was computed over.",
        LEFT,
        7.5,
        FAINT,
    )


def _grades(cursor: Cursor, scorecard: Scorecard | None) -> None:
    if scorecard is None or not scorecard.indicators:
        return
    _heading(cursor, "Grades")

    _label(cursor, "indicator", LEFT)
    _label(cursor, "verdict", LEFT + 250)
    _right(cursor.page, "LEVEL", cursor.y, REGULAR, 6.5, FAINT, tracking=1.1)
    cursor.down(6)
    cursor.rule(grey=0.55)
    cursor.down(13)

    for indicator in scorecard.indicators:
        reason = wrap(indicator.reason or "", REGULAR, 8, COLUMN) if indicator.reason else []
        cursor.need(22 + 10.5 * len(reason))
        cursor.page.text(LEFT, cursor.y, indicator.id, REGULAR, 8.5, INK)
        cursor.page.text(LEFT + 250, cursor.y, indicator.verdict, REGULAR, 8.5, MUTED)
        _right(
            cursor.page,
            indicator.level or " or ".join(indicator.between) or "none",
            cursor.y,
            BOLD,
            9,
            INK,
        )
        cursor.down(11)
        for line in reason:
            cursor.page.text(LEFT, cursor.y, line, REGULAR, 8, FAINT)
            cursor.down(10.5)
        cursor.down(1)
        cursor.rule(grey=0.92)
        cursor.down(12)

    cursor.down(2)
    _paragraph(
        cursor,
        f"Graded on the ladder {', '.join(scorecard.levels)} at access tier "
        f"{scorecard.access_tier}. A ceiling caps what a tier may claim whatever it "
        f"measured.",
        LEFT,
        7.5,
        FAINT,
    )


def _colophon(cursor: Cursor, report: Report) -> None:
    cursor.need(56)
    cursor.down(20)
    cursor.rule(grey=0.55)
    cursor.down(14)
    _paragraph(
        cursor,
        "Every figure in this document is read from the bundle it describes and none is "
        "recomputed here. A grade says what the evidence supports and is not an approval. "
        "The interval on a rate is sampling error and covers neither the fit of the item "
        "set to deployment nor the error of whatever decided each outcome.",
        LEFT,
        7.5,
        MUTED,
    )


def _footers(pages: list[Page], report: Report) -> None:
    stamp = f"touchstone {report.touchstone_version}"
    short = (report.bundle_sha256 or "unsealed")[:12]
    for number, page in enumerate(pages, start=1):
        page.rule(LEFT, BOTTOM - 18, COLUMN, HAIRLINE)
        page.text(LEFT, BOTTOM - 30, f"{stamp}   {short}", MONO, 7, FAINT)
        _right(page, f"{number} of {len(pages)}", BOTTOM - 30, REGULAR, 7, FAINT)


def build(report: Report, estimates: Estimates | None, scorecard: Scorecard | None) -> bytes:
    """The whole document, as PDF bytes."""
    cursor = Cursor()
    _masthead(cursor, report)
    _findings(cursor, report)
    _measurements(cursor, estimates)
    _grades(cursor, scorecard)
    _colophon(cursor, report)
    _footers(cursor.pages, report)
    return render(cursor.pages)
