#!/usr/bin/env python3
"""Reject commit messages that break the rules in CONTRIBUTING.md."""

import re
import sys
from pathlib import Path

SUBJECT_SOFT = 50
SUBJECT_HARD = 72

BANNED_WORDS = {
    "comprehensive",
    "robust",
    "seamless",
    "seamlessly",
    "powerful",
    "cutting-edge",
    "state-of-the-art",
    "elegant",
    "blazing",
    "leverage",
    "leverages",
    "delve",
    "utilise",
    "utilize",
    "holistic",
    "streamline",
    "unlock",
    "empower",
    "revolutionary",
    "game-changing",
}

BANNED_PATTERNS = [
    (r"[—–]", "em dash or en dash"),
    (r"(?i)co-authored-by:.*(claude|copilot|gpt|cursor|codex)", "AI attribution"),
    (r"(?i)generated with", "AI attribution"),
    (r"(?i)\bas an ai\b", "AI voice"),
    (r"[\U0001F300-\U0001FAFF☀-➿]", "emoji"),
]

PAST_TENSE = re.compile(
    r"^(added|fixed|updated|removed|changed|refactored|created|"
    r"implemented|adds|fixes|updates|removes|changes|implements)\b"
)

SLOGAN = re.compile(r",\s+not\b")

TRACKER = re.compile(r"#\d+|\b[A-Z][A-Z0-9]{1,9}-\d+\b")
"""Rule 8. A `#12` or a `PROJ-451` in the subject spends characters of the 50 that scanning
`git log --oneline` has on a string only useful once somebody has already found the commit.
The uppercase half is what a tracker key looks like and is not what this repository writes:
`sha256` is lowercase everywhere here, so it does not collide."""


def check(message: str) -> list[str]:
    lines = message.rstrip().splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            body_start = i
            break
    else:
        body_start = len(lines)
    lines = [ln for ln in lines[:body_start]]
    if not lines or not lines[0].strip():
        return ["empty commit message"]

    subject = lines[0]
    errors = []

    if len(subject) > SUBJECT_HARD:
        errors.append(f"subject is {len(subject)} chars, hard limit {SUBJECT_HARD}")
    elif len(subject) > SUBJECT_SOFT:
        errors.append(f"subject is {len(subject)} chars, keep it under {SUBJECT_SOFT}")

    if subject.endswith("."):
        errors.append("subject ends with a full stop")

    if subject[:1].isupper():
        errors.append("subject starts with a capital, use lowercase")

    if PAST_TENSE.match(subject.lower()):
        word = subject.split()[0]
        errors.append(f"subject is not imperative, write 'add' not '{word}'")

    if SLOGAN.search(subject):
        errors.append("subject is an 'x, not y' slogan, describe the change")

    found = TRACKER.search(subject)
    if found:
        errors.append(f"subject carries the issue reference '{found.group()}', put it in the body")

    if len(lines) > 1 and lines[1].strip():
        errors.append("no blank line between subject and body")

    for i, line in enumerate(lines[2:], start=3):
        if len(line) > SUBJECT_HARD:
            errors.append(f"body line {i} is {len(line)} chars, wrap at {SUBJECT_HARD}")

    text = "\n".join(lines)
    for pattern, label in BANNED_PATTERNS:
        if re.search(pattern, text):
            errors.append(f"contains {label}")

    words = set(re.findall(r"[a-z-]+", text.lower()))
    for banned in sorted(BANNED_WORDS & words):
        errors.append(f"contains marketing adjective '{banned}'")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_commit_msg.py <path-to-message>", file=sys.stderr)
        return 2

    errors = check(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not errors:
        return 0

    print("commit message rejected:", file=sys.stderr)
    for error in errors:
        print(f"  {error}", file=sys.stderr)
    print("\nsee CONTRIBUTING.md", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
