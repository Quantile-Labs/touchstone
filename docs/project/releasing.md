---
title: Releasing
description: How touchstone-dqi publishes from CI with PyPI trusted publishing.
---

# Releasing

Both packages publish from CI using PyPI trusted publishing. No API token is stored
anywhere, and the publishing identity is this repository rather than a person.

## What claims a name

**A pending trusted publisher does not reserve anything.** PyPI's own documentation is
explicit: a pending publisher "does not create a project or reserve a project's name until
it is actually used to publish", and if someone else registers the name first, the pending
publisher is invalidated. Only an upload claims a name.

Claiming under a personal account is not a dead end. PyPI supports transferring a project
owned by an individual into an organization later, so waiting for organization approval is
not a prerequisite for holding the name.

## One-time setup on PyPI

`touchstone-dqi` is the only package. Its trusted publisher is configured and it is
published; this section is here for the day it has to be set up again.

| Field | Value |
|---|---|
| PyPI project name | `touchstone-dqi` |
| Owner | `Quantile-Labs` |
| Repository | `touchstone` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

Type these into the form rather than pasting. A leading space copied out of a table cell
is rejected as `Environment name may not start with whitespace`.

## There is no `dqi` package

`dqi` cannot be registered on PyPI. It is confusable with `dql`, an unrelated DynamoDB
package, under PyPI's ultranormalization, which treats `i` and `l` as the same character.
The rule is automatic and `dql` is a legitimate project, so there is nothing to appeal.

**It is blocked for everyone, so there is nothing to lose by not holding it.** An alias
package existed only so `pip install dqi` would work. Since it cannot, the alias was
removed rather than published under a name no one would type. DQI is the name of the
standard and the standard lives at a URL.

The GitHub environment named `pypi` exists. It was created on 25 Aug 2026 and nothing
needs doing there unless it is deleted.

**It allows the branch `main` and the tag pattern `v*`, and it needs both.** A release
event runs with the ref `refs/tags/v0.0.1`, not a branch, so an environment restricted to
`main` alone blocks the publish job before its first step, with no log and no steps in the
run. `main` is still needed for a manual `workflow_dispatch`.

## Publishing

Publishing happens on every GitHub release:

```bash
git tag v0.1.0 && git push origin v0.1.0
gh release create v0.1.0 --generate-notes
```

## Version numbers

A version on PyPI cannot be replaced or reused. Bump, do not overwrite.

Check what is about to become permanent before the first upload of any version:

```bash
.venv/bin/pyproject-build && .venv/bin/twine check dist/*
tar -tzf dist/touchstone_dqi-*.tar.gz | grep -iE "CONTEXT|NIGERIA|ASQI|DESIGN|BUILD-PLAN"
```

The sdist is built from the git tree, so a planning document that reached the repository
would ship. The second command is the check that it did not.
