---
title: Uncertainty and assumptions
description: >-
  The uncertainty budget each whole-sample figure carries, and the assumptions the
  estimators rest on, each with what checking it found.
---

# Uncertainty and assumptions

An interval accounts for sampling. `estimates.json` also lists every other source of
uncertainty this tool knows about, sizing each one where the rows allow and marking the
rest `unquantified`.
{ .lede }

```console
$ touchstone estimate run-004 --by rung
...
  not quantified: marking, item selection, item leakage, endpoint identity
  assumptions not checked: unidimensional, functional form, independent items
```

## The budget

Every whole-sample figure gets one entry in `uncertainty`, in the shape of the uncertainty
budget in JCGM 100:2008 (the GUM). Each component has a `source`, a `magnitude`, a `method`
and, where there is one, a `reference`.

```json
{
  "metric": "correct",
  "pack_id": "example_pack",
  "point": 0.6667,
  "components": [
    {"source": "completion_sampling", "magnitude": 0.0, "method": "anova_moment, the completion term over 60 items", "reference": "NIST AI 800-3, ..."},
    {"source": "item_sampling", "magnitude": 0.0614, "method": "anova_moment, the item term over 60 items", "reference": "NIST AI 800-3, ..."},
    {"source": "marking", "magnitude": "unquantified", "method": "no agreement study between how outcomes were marked and a reference marking", "reference": null}
  ]
}
```

A magnitude is a standard uncertainty, on the same scale as the figure. The quantified
components are independent and combine in quadrature.

| Source | Sized from |
|---|---|
| `completion_sampling`, `item_sampling` | the [variance split](replicates.md#which-of-the-two-more-replicates-buys), where the plan ran replicates |
| `sampling` | the stored interval, half its width over `z`, where it did not |
| `marking` | nothing yet. Needs an agreement study against a reference marking |
| `item_selection` | nothing yet. Needs a measure of how well the items represent real use |
| `item_leakage` | nothing yet. Needs a contamination test |
| `endpoint_identity` | nothing yet. Needs a check that the endpoint is the system named |

The unsized sources are listed on purpose. A budget that listed only the components with
numbers would read as complete. `touchstone report` prints the whole budget.

## The assumptions

`assumptions` names the premises that NIST AI 800-3 section 6.2 says a regression-free
estimator fails silently on. NIST AI 800-2 ipd Practice 3.1 item 1 asks for them to be
reported together with the result of any check.

| Name | What is assumed | Checked by |
|---|---|---|
| `unidimensional` | the items of a figure measure one construct | not checked. Needs a latent variable model |
| `functional_form` | each item has one probability of success, and each trial is a draw at that probability | Pearson's chi-square test of homogeneity across replicate rates, per outcome |
| `independent_items` | items are independent once scored | not checked. Needs item groups the rows do not carry |

`result` is `consistent`, `violated` or `not checked`. `consistent` means the test found no
evidence against the assumption, which is weaker than showing that it holds. A `violated`
functional form means the system changed between replicates, while the interval treats
every trial as coming from one population.

Replicates of one plan draw the same items, so their rates move together, and the test
treats them as independent. That makes it conservative. A small p-value is at least as
strong as it looks.
