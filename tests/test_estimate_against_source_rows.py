"""The credential again, against the rows themselves rather than their published counts.

tests/test_estimate_credential.py rebuilds the sample from the counts printed in the
published results, because the study is private and this repository is public. That
proves the estimator and the rollup. It does not prove the loader against real data, and
real data is where an item arrives with a field the fixture never thought to write.

This test closes that gap without publishing anything. It is skipped unless the source
table is on the machine and named explicitly:

    TOUCHSTONE_SOURCE_ROWS=/path/to/points_evidence.csv .venv/bin/pytest -q

The path is never written down here, so nothing about where the study lives leaks into a
public repository, and CI skips this file the way every other machine does.

The two columns are the ones 04-analysis/02_primary.py uses to build the same rungs:
`is_hybas_entry` separates real gauges from undocumented inventory entries, and
`generous` is the evidence outcome under the most permissive of the three definitions.
"""

import csv
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from touchstone.cli import app

SOURCE = os.environ.get("TOUCHSTONE_SOURCE_ROWS")

pytestmark = pytest.mark.skipif(
    not SOURCE, reason="set TOUCHSTONE_SOURCE_ROWS to the published points table to run this"
)


def _flag(value: str) -> bool:
    return value.strip().lower() == "true"


def _records():
    with Path(SOURCE).open() as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            yield {
                "item_id": row.get("unique_gauge_id") or f"point.{index}",
                "stratum": {
                    "rung": "hybas_entry" if _flag(row["is_hybas_entry"]) else "real_gauge"
                },
                "outcome": {"evidenced": _flag(row["generous"])},
            }


def test_the_published_number_comes_back_out_of_the_source_rows(tmp_path):
    records = list(_records())
    (tmp_path / "items.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    )

    result = CliRunner().invoke(app, ["estimate", str(tmp_path), "--by", "rung"])
    assert result.exit_code == 0, result.output

    # 05-results/primary.json, secondary_gauge_count_coverage. The same two lines the
    # README quotes and the same two the counts-based credential test reproduces.
    assert "7.8% (95% CI 6.9-8.8%, n=3090)" in result.output
    assert "3.6% (95% CI 3.2-4.0%, n=6772)" in result.output

    written = json.loads((tmp_path / "estimates.json").read_text())
    real = next(
        entry
        for entry in written["estimates"]
        if entry["metric"] == "evidenced" and entry["stratum"] == {"rung": "real_gauge"}
    )
    assert (real["k"], real["n"]) == (242, 3090)
    assert (real["point"], real["low"], real["high"]) == (
        0.07831715210355987,
        0.06935898244776396,
        0.0883225226428651,
    )
