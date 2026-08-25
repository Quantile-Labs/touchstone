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

For each package name, add a pending trusted publisher at
https://pypi.org/manage/account/publishing/ with these values.

| Field | touchstone-dqi | dqi |
|---|---|---|
| PyPI project name | `touchstone-dqi` | `dqi` |
| Owner | `Quantile-Labs` | `Quantile-Labs` |
| Repository | `touchstone` | `touchstone` |
| Workflow | `publish.yml` | `publish.yml` |
| Environment | `pypi` | `pypi` |

The GitHub environment named `pypi` exists and is restricted to `main`. It was created
on 25 Aug 2026; nothing needs doing there unless it is deleted.

## Publishing

`touchstone-dqi` publishes on every GitHub release:

```bash
git tag v0.0.1 && git push origin v0.0.1
gh release create v0.0.1 --generate-notes
```

`dqi` is an alias package and changes rarely. Publish it by hand:

```bash
gh workflow run publish.yml -f package=dqi
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
