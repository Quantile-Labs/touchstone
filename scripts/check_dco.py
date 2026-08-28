#!/usr/bin/env python3
"""Reject a commit that carries no Developer Certificate of Origin sign off.

Separate from `check_commit_msg.py` on purpose. That script judges a message on its own
and this one has to compare the trailer against the commit's author, which is a fact only
git holds, so it takes the author as a second argument when there is one to check.
"""

import re
import sys
from pathlib import Path

SIGNED_OFF = re.compile(r"^Signed-off-by: (?P<name>.+?) <(?P<email>[^<>@\s]+@[^<>\s]+)>$")
"""Deliberately strict. `git commit -s` writes exactly this shape, and a hand-typed
approximation that a DCO bot would reject is better caught here than after the push."""


def check(message: str, author: str | None = None) -> list[str]:
    trailers = [SIGNED_OFF.match(line.strip()) for line in message.splitlines()]
    signers = {f"{m.group('name')} <{m.group('email')}>" for m in trailers if m}

    if not signers:
        return [
            "no 'Signed-off-by:' trailer, commit with 'git commit -s'",
            "see the Developer Certificate of Origin at https://developercertificate.org/",
        ]

    if author is not None and author not in signers:
        return [
            f"author '{author}' did not sign off",
            "signed off by: " + ", ".join(sorted(signers)),
        ]

    return []


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: check_dco.py <path-to-message> [author]", file=sys.stderr)
        return 2

    author = sys.argv[2] if len(sys.argv) == 3 else None
    errors = check(Path(sys.argv[1]).read_text(encoding="utf-8"), author)
    if not errors:
        return 0

    print("commit rejected:", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    print("\nsee CONTRIBUTING.md", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
