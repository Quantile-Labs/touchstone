---
title: Reporting
description: >-
  A conformance statement over a bundle, stating what it holds against each
  practice item and what it does not, as a PDF.
---

# Reporting

A bundle is JSON, JSON Lines and hashes. That is the right substrate for evidence and it is
not what an auditor, a procurement reviewer or a risk team reads. `touchstone report` sets
the same bundle as a document those readers can open.
{ .lede }

```console
$ touchstone report ./run-004
./run-004.pdf: 10 practice item(s), 3 not met
```

The statement is written beside the bundle, never inside it. A file the manifest does not
record makes `verify` report the bundle as tampered with, so the command refuses that path
rather than breaking the thing it describes.

## What it states

Each practice item gets a line saying what the bundle holds against it and one of three
statuses: `met`, `not met`, `not applicable`. There is no fourth. A partial credit column is
where a conformance report stops being readable, because every line becomes partial and the
reader has to grade the grader.

Six items come from NIST AI 800-2 ipd, Practices 3.1 to 3.3:

| Reference | Item |
|---|---|
| 3.1.3 | Every reported figure carries an interval and names the method |
| 3.1.4 | Sources of variation are decomposed, or named as unquantified |
| 3.2.2 | Item-level results are present, not only aggregates |
| 3.2.3 | The cost of producing the result is recorded |
| 3.2.5 | The evaluation code and the image that ran are identified and obtainable |
| 3.3 | Claims are qualified by what the evidence supports |

Four more are added here, because the practices as summarised elsewhere miss them: the
estimand each interval covers is named, the assumption checks behind each estimator are
recorded, figures from packs measuring different things are not aggregated, and movement
against an earlier evaluation is estimated as a paired difference.

## It reports failures as failures

A statement listing only what passed is marketing, and the first reviewer who diffs it
against the practice list will say so. Two items fail on every bundle this tool produces
today.

**Costs are not recorded.** Nothing in a bundle holds tokens, wall time or spend, so a
reader cannot tell what a narrower interval would have cost to buy.

**Assumption checks are not recorded.** The bundle names the estimator that ran and not
whether its premises hold. A Wilson interval over a sample that is not exchangeable is
arithmetic on the wrong model, and nothing here would say so.

A third fails until `example_pack` reaches a registry: an image pinned by digest is
identified, and a reader holding the bundle and no registry still cannot pull it.

An empty directory produces a statement in which eight of the ten items fail. That is the
intended behaviour and there is a test for it.

## Nothing on the page is recomputed

Every figure is read from `estimates.json` and `scorecard.json`. The document sets numbers
and never derives them, because a second implementation of the arithmetic sitting in the
one output nobody thinks to re-check is how two figures for the same thing get published.
A test pulls the text back out of the finished PDF and maps every rate, bound and
denominator on it to a field in the bundle.

## The file

One PDF, no external resources, and no dependency behind it. The base fourteen fonts and a
content stream are enough for a page of text, rules and tables, and a PDF library wanting
system libraries on the host would cost the offline install that CI tests on every change.

The bytes are deterministic. There is no creation date and no document identifier, so the
same bundle produces the same statement twice and two readers can agree they are holding
the same one.

```console
$ touchstone report ./run-004 -o a.pdf && touchstone report ./run-004 -o b.pdf
$ shasum -a 256 a.pdf b.pdf
c64de425...  a.pdf
c64de425...  b.pdf
```

## Reading it as data

`--json` emits the findings in the usual envelope, with each unmet item as a warning. The
command still exits zero: a statement that found failures is a statement that worked.

```console
$ touchstone report ./run-004 --json
```

See [Machine-readable output](../basics/cli.md#machine-readable-output).
