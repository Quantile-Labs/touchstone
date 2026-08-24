# Releasing

Both packages publish from CI using PyPI trusted publishing. No API token is stored
anywhere, and the publishing identity is this repository rather than a person.

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

Then create a GitHub environment named `pypi` in repository settings and restrict it
to the `main` branch.

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
