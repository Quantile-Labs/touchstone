---
title: Audit indicators
description: >-
  Indicators a person assesses rather than the bundle reports, and how the engine
  refuses to grade them itself while still capping what they may claim.
---

# Audit indicators

Some things cannot be read off `items.jsonl`. Whether someone subject to an adverse decision
can obtain the reason and challenge it, or whether the artefact evaluated is the artefact
deployed, are both read off an **organisation** rather than off a file.
{ .lede }

An audit indicator carries a question, a person answers it, and the engine checks the answer
without pretending to have computed it.

## In the card

```yaml
indicators:
  - id: artefact_provenance
    name: "Is the artefact evaluated the artefact deployed?"
    metric:
      source: audit
      question: >-
        Show that the image, weights or endpoint evaluated here is the one serving
        production traffic. Name what was examined.
    tier_ceilings:
      black_box: "C"
      grey_box: "A"
```

Note there is **no `assessment`**. An audit indicator is graded by its assessor, and a
threshold applied to a judgment that never produced a number is a category error. A card
that puts rules on one is refused.

The `question` lives in the card rather than in the responses, so **two audits of the same
index answered the same question.**

## In the responses

A separate file, keyed by indicator id:

```yaml title="audit.yaml"
audit_name: "Q3 2026 provenance review"
assessor: "A. Reviewer, Internal Audit"
assessed_utc: "2026-08-20T14:00:00Z"

responses:
  artefact_provenance:
    level: "B"
    evidence: >-
      Compared the image digest in plan.lock.json against the digest recorded in the
      deployment manifest for prod-eu-1 on 2026-08-19. They match. Did not verify that
      the manifest is what the cluster is actually running.
```

```console
$ touchstone grade ./run-004 --score-card card.yaml --audit audit.yaml
```

## Why it is a separate file

**The judgment and the rubric are written by different people at different times.** Keeping
them in one file would mean the person filling in the answers editing the file that defines
what the answers mean, which is the arrangement the rest of this tool exists to prevent.

## What is required, and why

| Field | Required | Why |
|---|---|---|
| `assessor` | yes | An audit outcome is a person's judgment, and **a judgment with no author cannot be questioned.** |
| `assessed_utc` | yes | When. |
| `level` | yes | Must be on the card's own ladder. |
| `evidence` | yes | **An audit level with nothing behind it is an opinion**, and this file travels into the bundle. |

`evidence` is the field a reviewer argues with. Every response carries it for the same
reason every rate carries its denominator.

An indicator id the score card does not declare is an **error**, not a warning. It is either
a typo or an audit of a different card, and both produce a bundle whose grades came from
somewhere nobody can identify.

## The engine still refuses to grade it

It takes the level the assessor recorded, checks it is on the ladder the card declares, and
**applies the same access tier ceiling as every computed indicator.**

So a human judgment cannot claim more than the access allowed. `artefact_provenance` capped
at `C` for a black-box evaluation is capped there whoever assessed it and however confident
they were.

## Into the bundle

`grade` copies the responses file into the run, and records its hash:

```json
{
  "audit_name": "Q3 2026 provenance review",
  "audit_assessor": "A. Reviewer, Internal Audit",
  "audit_sha256": "4f2c…",
  "indicators": [
    {
      "id": "artefact_provenance",
      "verdict": "graded",
      "level": "C",
      "uncapped_level": "B",
      "ceiling": "C",
      "ceiling_reason": "access_tier",
      "audit": {
        "level": "B",
        "evidence": "Compared the image digest in plan.lock.json against …"
      }
    }
  ]
}
```

A grade that cannot be recomputed from the bundle is not evidence, so the file it came from
travels with it. **An audited level is somebody's judgment, and the bundle names whose and
which version.**

The response is kept whole, so the level and the evidence behind it travel together into the
report.

## Without `--audit`

Audit indicators come out `ungraded`.

That is a true statement, and it is the right default: a bundle produced without an
assessment should say the assessment was not done, not quietly award a floor level or omit
the indicator.
