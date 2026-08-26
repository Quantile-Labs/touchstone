<!--
The description says what changed and why. Not how: the diff says how.
CONTRIBUTING.md has the commit rules, and the commit-messages job checks every
commit in this pull request against them.
-->

## What changed



## Why



## Checks

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy`
- [ ] `uv run pytest -q`
- [ ] Behaviour I documented has a test. See CONTRIBUTING.md, Documentation.

<!--
Tick this one only if it applies, and say what breaks in the description.
A change under src/touchstone/contracts/ is a major version.
-->
- [ ] This changes a contract in `src/touchstone/contracts/`
