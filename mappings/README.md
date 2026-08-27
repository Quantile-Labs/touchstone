# Framework mappings

Which regulatory obligation each DQI indicator produces evidence for, one file per
jurisdiction, every row read against the primary source and dated.

**These are draft citations for a draft specification.** DQI Specification v0.1 is not
published. Nothing here licenses, certifies or approves anything, and a DQI level is not a
compliance verdict: the mapping says which obligation a measurement is evidence for, and
whether that evidence satisfies a regulator is the regulator's judgment.

## What a row must carry

| Field | Meaning |
|---|---|
| `framework` | the instrument, by stable id |
| `clause` | the specific provision, read against the primary source |
| `strength` | `direct` where the indicator evidences the obligation, `supporting` where it contributes, `unknown` where the provision was not read |
| `checked` | the date the citation was verified, `null` where it was not |
| `by` | who verified it |
| `quote` | the words relied on |

`quote` is what makes a row arguable. A clause reference on its own asks a reader to take
the reading on trust, and the whole point of this repository is that they should not have
to. `tests/test_mappings.py` enforces the shape.

## What is here

| File | State |
|---|---|
| `eu.yaml` | Regulation (EU) 2024/1689, 11 articles read in full |
| `ng.yaml` | five Nigerian instruments, four read in full, one read through the regulator's own directive |
| `iso.yaml` | **no citations.** ISO/IEC 42001:2023 is sold rather than published and was not read |

An unread framework keeps a file. It records what was attempted, what blocked it and what
closes it, so that a later reader can tell an absence from an oversight.

## Adding a jurisdiction

Write `<jurisdiction>.yaml` in the shape above and open a pull request. It touches no code.

**Read the instrument.** Clause numbers are widely reproduced in summaries, consultancy
notes and marketing, and none of that is a primary source. A citation written from memory
into a compliance artefact is worse than an absent one, because a reader cannot tell the
difference until they check. If you could not obtain the text, say so in the row and leave
`checked` null.

## Scope

Every row is bounded by the instrument's own scope. The EU rows apply to high-risk AI
systems under Annex III and to no others; the Nigerian lending rows apply to a lender in
scope of those regulations. A report that cites a row without establishing scope is citing
a clause that binds somebody else.
