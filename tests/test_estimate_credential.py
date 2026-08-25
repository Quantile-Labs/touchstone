"""The credential for the statistics module.

`03-BUILD-PLAN.md` M2: done when `touchstone estimate` reproduces a number already
published in QL-2026-01 to the printed precision, from item records, with its interval.

The number is gauge-count coverage of the evidence base, the Gate F comparator. It was
published in `05-results/primary.json` as `secondary_gauge_count_coverage`:

    rung_2_real_gauges   evidenced 242, n 3090, wilson
                         [0.07831715210355987, 0.06935898244776396, 0.0883225226428651]
    rung_2b_all_points   evidenced 242, n 6772, wilson
                         [0.03573538098050797, 0.0315707728074542,  0.040426423821227325]

The published run is a private laboratory study, so its 6772 item-level rows do not live
in this repository. The counts above do, and the fixture rebuilds records that carry them:
every evidenced point is a real gauge, because an undocumented `hybas_` entry cannot hold
a metric by construction. Reproducing both rungs from one set of records is what shows the
rollup groups correctly as well as that the estimator is right.
"""

import json

from typer.testing import CliRunner

from touchstone.cli import app

REAL_GAUGES = 3090
HYBAS_ENTRIES = 3682
EVIDENCED = 242

PUBLISHED_RUNG_2 = (0.07831715210355987, 0.06935898244776396, 0.0883225226428651)
PUBLISHED_RUNG_2B = (0.03573538098050797, 0.0315707728074542, 0.040426423821227325)


def _items(path):
    """One record per African forecast point, carrying the published counts."""
    records = []
    for index in range(REAL_GAUGES):
        records.append(
            {
                "item_id": f"gauge.{index:04d}",
                "stratum": {"rung": "real_gauge"},
                "outcome": {"evidenced": index < EVIDENCED},
            }
        )
    for index in range(HYBAS_ENTRIES):
        records.append(
            {
                "item_id": f"hybas.{index:04d}",
                "stratum": {"rung": "hybas_entry"},
                "outcome": {"evidenced": False},
            }
        )
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))


def test_estimate_reproduces_a_published_number(tmp_path):
    _items(tmp_path / "items.jsonl")

    result = CliRunner().invoke(app, ["estimate", str(tmp_path), "--by", "rung"])

    assert result.exit_code == 0, result.output
    assert "7.8% (95% CI 6.9-8.8%, n=3090)" in result.output


def test_estimates_json_carries_the_interval_and_names_its_estimator(tmp_path):
    _items(tmp_path / "items.jsonl")

    result = CliRunner().invoke(app, ["estimate", str(tmp_path), "--by", "rung"])
    assert result.exit_code == 0, result.output

    written = json.loads((tmp_path / "estimates.json").read_text())
    by_key = {
        (entry["metric"], tuple(sorted(entry["stratum"].items()))): entry
        for entry in written["estimates"]
    }

    overall = by_key[("evidenced", ())]
    assert (overall["point"], overall["low"], overall["high"]) == PUBLISHED_RUNG_2B
    assert (overall["k"], overall["n"]) == (EVIDENCED, REAL_GAUGES + HYBAS_ENTRIES)

    real = by_key[("evidenced", (("rung", "real_gauge"),))]
    assert (real["point"], real["low"], real["high"]) == PUBLISHED_RUNG_2
    assert (real["k"], real["n"]) == (EVIDENCED, REAL_GAUGES)

    # 02-DESIGN.md section 6 rule 3: the bundle is self-describing, so the arithmetic can
    # be redone in R or a spreadsheet without this code.
    assert real["estimator"] == "wilson"
    assert real["parameters"]["z"] == 1.96
    assert real["reference"]
