"""Locale belongs in packs and mappings, never in the engine.

See CONTRIBUTING.md. A country code here would make Touchstone usable only where we
happen to work, which is the opposite of the point.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

CODES = re.compile(r"""["'](NG|KE|GH|ZA|US|GB|SG|NL|DE|FR|BR|IN|ID)["']""")
"""Case sensitive, and deliberately so. ISO 3166 codes are written upper case, while
`"id"` is a field name in half the contracts in this tree. Matching those too caught
`{"id": indicator.id}` in `grade.py` and would have taught the next person to route around
the guard rather than read it."""

NAMES = re.compile(
    r"""\b(nigeria|nigerian|kenya|kenyan|ghana|naira|NDPC|NITDA|FCCPC|CBN)\b""",
    re.IGNORECASE,
)
"""A regulator's name is never a field name, so this half stays case insensitive."""


def test_no_country_or_regulator_logic_in_src():
    offenders = []
    for path in SRC.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if CODES.search(line) or NAMES.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()}")
    assert not offenders, "locale leaked into src/:\n" + "\n".join(offenders)


def test_the_guard_still_catches_what_it_is_for():
    """A guard nobody tests is a guard that quietly stops matching. This is the specific
    failure 01-ASQI-TEARDOWN.md section 4 defect 5 is about."""
    for leak in ['locale = "NG"', 'if code == "KE":', "# nigerian name order", "FCCPC rules"]:
        assert CODES.search(leak) or NAMES.search(leak), leak
