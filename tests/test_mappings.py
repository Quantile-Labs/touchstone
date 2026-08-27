"""Every mapping row is checkable, or says that it is not.

Section 8 of the DQI specification governs what a mapping file contains, and a file that
nothing reads is prose. These tests are that reader. The load-bearing one is
`test_a_checked_row_carries_its_quote`: a clause reference with no quote asks a reviewer to
take the reading on trust, which is the failure this whole repository exists to avoid.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

MAPPINGS = Path(__file__).resolve().parent.parent / "mappings"
STRENGTHS = {"direct", "supporting", "unknown"}
REQUIRED = {"framework", "clause", "strength", "checked", "by"}


def mapping_files():
    return sorted(MAPPINGS.glob("*.yaml"))


def rows(path):
    document = yaml.safe_load(path.read_text())
    for indicator, entries in (document.get("indicators") or {}).items():
        for entry in entries:
            yield indicator, entry


def test_there_are_mappings():
    assert mapping_files(), "mappings/ holds no jurisdiction files"


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_every_row_carries_the_required_fields(path):
    for indicator, row in rows(path):
        missing = REQUIRED - set(row)
        assert not missing, f"{path.name} {indicator}: row is missing {sorted(missing)}"


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_strength_is_one_of_three(path):
    for indicator, row in rows(path):
        assert row["strength"] in STRENGTHS, (
            f"{path.name} {indicator}: strength {row['strength']!r} is not one of "
            f"{sorted(STRENGTHS)}"
        )


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_a_checked_row_carries_its_quote(path):
    """A row that claims a reading has to show the words it read.

    `note` is accepted in place of `quote` where the row rests on a clause heading or on a
    reading rather than on a sentence, because forcing a quote there would produce one that
    does not say what the row says.
    """
    for indicator, row in rows(path):
        if row["checked"] is None:
            continue
        assert row.get("quote") or row.get("note"), (
            f"{path.name} {indicator}: {row['clause']} is checked and carries neither a "
            "quote nor a note saying what was read"
        )


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_an_unread_row_is_not_dated(path):
    """`unknown` means nobody read it, so it may not carry a date or an attribution."""
    for indicator, row in rows(path):
        if row["strength"] != "unknown":
            continue
        assert row["checked"] is None, (
            f"{path.name} {indicator}: {row['clause']} is unread and carries a check date"
        )
        assert row["by"] is None, (
            f"{path.name} {indicator}: {row['clause']} is unread and names a checker"
        )


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_a_checked_row_names_who_checked_it(path):
    for indicator, row in rows(path):
        if row["checked"] is None:
            continue
        assert row["by"], f"{path.name} {indicator}: {row['clause']} is checked by nobody"


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_check_dates_are_dates_and_are_not_in_the_future(path):
    for indicator, row in rows(path):
        if row["checked"] is None:
            continue
        checked = row["checked"]
        if isinstance(checked, str):
            checked = date.fromisoformat(checked)
        assert checked <= date.today(), (
            f"{path.name} {indicator}: {row['clause']} was checked on {checked}, "
            "which has not happened yet"
        )


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_every_framework_a_row_names_is_declared(path):
    document = yaml.safe_load(path.read_text())
    declared = set()
    if "framework" in document:
        declared.add(document["framework"]["id"])
    for entry in document.get("frameworks") or []:
        declared.add(entry["id"])
    for entry in document.get("frameworks_unread") or []:
        declared.add(entry["id"])
    for indicator, row in rows(path):
        assert row["framework"] in declared, (
            f"{path.name} {indicator}: names framework {row['framework']!r}, which the "
            f"file does not declare. Declared: {sorted(declared)}"
        )


@pytest.mark.parametrize("path", mapping_files(), ids=lambda p: p.name)
def test_an_unread_framework_carries_what_closes_it(path):
    document = yaml.safe_load(path.read_text())
    entries = list(document.get("frameworks_unread") or [])
    if document.get("status") == "unread":
        entries.append(document["framework"])
    for entry in entries:
        assert entry.get("blocked_by"), f"{path.name}: {entry['id']} does not say what blocked it"
        assert entry.get("to_close"), f"{path.name}: {entry['id']} does not say what closes it"
