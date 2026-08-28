# Governance

This document describes how Touchstone is run today. It is deliberately short,
because a governance document that describes a structure nobody has built is worse
than none: it is the first thing a careful reader checks and the first thing that
discredits everything beside it.

## Where the project stands

**Touchstone has one maintainer**, Kayode Adeniyi, working at Quantile Labs, which
holds the copyright. There is no steering committee, no technical oversight body and
no vote, because there is nobody to hold one with. Every decision below is currently
made by one person.

This is written down so that a reader evaluating the project can price it correctly.
A single-maintainer project carries bus-factor risk and carries the risk that the
company behind it changes its mind. Both are real here.

## The two things being governed

They are separate on purpose and they are governed differently.

**Touchstone, the instrument.** This repository. Apache 2.0, open to contribution,
and everything below applies to it.

**The DQI, the standard it computes.** The specification is drafted and unpublished,
and it is currently written by Quantile Labs alone. A standard controlled by one
company is a weaker standard than one a buyer, a regulator and a vendor all had a
hand in, and moving it to independent stewardship is an open question rather than a
commitment. **Nothing in this document claims the specification is independently
governed**, and no page of the documentation site should claim it either.

The naming rule follows from the split: the tool versions as `Touchstone 1.0` and the
standard as `DQI Specification v1.0`, and `DQI 1.0` alone is never written.

## Decisions, and where they are recorded

Rules here are code wherever a rule can be code, and the enforcement is the record.

| Decision | Made by | Recorded in |
|---|---|---|
| Any change to `src/`, `docs/` or `mappings/` | maintainer, through a pull request | the pull request and the commit |
| A change to a contract in `src/touchstone/contracts/` | maintainer, and it is a major version | the pull request, which has to say what breaks |
| A release | maintainer | a tag, a GitHub release, and `docs/project/releasing.md` |
| A regulatory citation in `mappings/` | whoever read the source, named on the row with the date they read it | the row, enforced by `tests/test_mappings.py` |
| The specification's thresholds | Quantile Labs | section 6.0 of the specification |

`main` is protected: every CI job must pass, history stays linear, and force pushes are
off. Administrators are exempt, so a direct push is possible when something has to
land, which makes the reviewed path the default rather than the only one. Every such
push is visible in the history.

## Contributing, and becoming a maintainer

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first. It is the authority on how a change
lands and what the linters expect.

**Anyone can contribute.** A pull request is reviewed on whether it is correct, whether
it is tested, and whether the documentation it touches is executed by a test.

**Commit access follows a track record**, not an application. Somebody who has landed
a handful of substantial changes and has shown the judgment the code review rules
describe will be offered it. The offer is made by the existing maintainers, which
today means one person, and the first such offer will replace this paragraph with a
real process.

## What Quantile Labs cannot do

This is the part worth reading if you are deciding whether to depend on Touchstone.

**The licence cannot be pulled.** Apache 2.0 is irrevocable for code already released.
Version 0.3.0 is Apache 2.0 forever, and so is every commit published under it.

**A future relicence cannot be done quietly.** Contributions arrive under the
[Developer Certificate of Origin](https://developercertificate.org/) rather than a
contributor licence agreement. A CLA would assign the rights that make a unilateral
relicence possible, and the DCO does not, so relicensing contributed code would need
every contributor's agreement. This is the point of choosing the DCO and it is the
commitment the rest of the independence argument rests on.

**A regulatory citation cannot be asserted without a source.** Every row in
`mappings/` carries the text it read, the date it was read and who read it, and
`tests/test_mappings.py` fails the build on a row that does not. An unread framework
has to say what blocked it and what would close it, which is why `mappings/iso.yaml`
is public, empty and explains itself.

## Changing this document

Through a pull request, like everything else. **Change it when the facts change**, and
in particular when a second maintainer arrives, when the specification moves to
independent stewardship, or when either stops being true.
