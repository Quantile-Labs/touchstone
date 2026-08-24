"""Locale belongs in packs and mappings, never in the engine.

See CONTRIBUTING.md. A country code here would make Touchstone usable only where we
happen to work, which is the opposite of the point.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

CODES = re.compile(
    r"""["'](NG|KE|GH|ZA|US|GB|SG|NL|DE|FR|BR|IN|ID)["']|"""
    r"""\b(nigeria|nigerian|kenya|kenyan|ghana|naira|NDPC|NITDA|FCCPC|CBN)\b""",
    re.IGNORECASE,
)


def test_no_country_or_regulator_logic_in_src():
    offenders = []
    for path in SRC.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if CODES.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()}")
    assert not offenders, "locale leaked into src/:\n" + "\n".join(offenders)
