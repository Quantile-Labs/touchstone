# Contributing

Read this before your first commit. The rules here are enforced by CI, not by review.

Four documents sit beside this one. [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) is the
Contributor Covenant and applies to every space this project uses.
[`SECURITY.md`](SECURITY.md) says how to report a vulnerability, and asks you not to
open a public issue for one. [`GOVERNANCE.md`](GOVERNANCE.md) says who decides and what
Quantile Labs has given up the ability to do. [`LICENSE`](LICENSE) is Apache 2.0.

## Signing your work

**Every commit needs a Developer Certificate of Origin sign off.** Pass `-s` and git
writes the trailer for you:

```bash
git commit -s -m "add wilson interval to rate estimator"
```

```
Signed-off-by: Ada Lovelace <ada@example.com>
```

That line certifies the [Developer Certificate of Origin](https://developercertificate.org/),
version 1.1: that you wrote the change or otherwise have the right to submit it under
Apache 2.0. Use your real name and the email git is configured with, because
`scripts/check_dco.py` compares the trailer against the commit author and the `dco` CI
job runs it over every commit in a pull request.

**There is no contributor licence agreement and there will not be one.** A CLA would
assign Quantile Labs the rights to relicense contributed code without asking you, and
the independence this project argues for is worth more than that option.
[`GOVERNANCE.md`](GOVERNANCE.md) has the reasoning.

Fix a commit you forgot to sign with `git commit --amend -s`, or a run of them with
`git rebase --signoff <base>`.

## Licence headers

Every file in `src/` opens with two lines:

```python
# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0
```

A new source file needs them, and `tests/test_spdx_headers.py` fails the build without
them. A root `LICENSE` covers the repository and does not travel with a file somebody
vendors into another tree, which is what the header is for.

## Commit messages

Write like an engineer with work to do. Short, factual, imperative.

```
add wilson interval to rate estimator
fix digest resolution for multi-arch images
drop unused seed parameter from plan loader
```

**Rules 1 to 8 are enforced by `scripts/check_commit_msg.py`, and so is the `X, not Y`
half of rule 9. The rest of rule 9 and all of rule 10 are not, and are marked so, because
a rule that claims enforcement it does not have teaches people to stop believing the
list.**

1. Subject is 50 characters or fewer. Hard limit 72.
2. Imperative mood. `add`, not `added` or `adds`.
3. Lowercase first word. No trailing full stop.
4. Body optional. Add one only to explain *why*, never to restate the diff.
   Wrap at 72. Blank line between subject and body.
5. **No em dashes or en dashes.** Anywhere. Use a comma or a full stop.
6. No marketing adjectives. The linter rejects: comprehensive, robust, seamless,
   powerful, cutting-edge, state-of-the-art, elegant, blazing, leverage, delve,
   utilise, holistic, streamline, unlock, empower.
7. No AI attribution. No `Co-Authored-By` for a tool, no `Generated with`, no emoji.
8. No issue-tracker noise in the subject. Put refs in the body.
9. **Describe the change, do not editorialise it.** *(half enforced)* The subject is a verb
   and the thing it acts on. No rhetorical shapes, and in particular no `X, not Y`, which
   reads as a slogan and says half as much as a plain description would. The linter
   rejects a subject with `, not` in it; whether the rest of a subject describes or
   editorialises is a judgment no regular expression makes.
10. **The body is prose.** *(not enforced)* Sentences that join with a comma and carry a
    clause. Short declaratives stacked one after another read as though nobody wrote them,
    which is a bad look on a repository about evidence.

**Why 50 characters.** `git log --oneline` is how the history gets read. A subject
that wraps is a subject nobody reads.

**Why the adjective list.** Those words carry no information about the change. If a
commit needs to say the work is good, the work is not good enough.

**Why the subject is boring on purpose.** Every one of these is real, from this
repository, and each one wasted the reader's attention on a shape instead of spending it
on a fact:

| Written | Should have been |
|---|---|
| `put trust at the front, not the sceptic` | `reframe readme around trust` |
| `cap and search per indicator, not per card` | `add per-indicator ceilings and stratum keys` |
| `lead the readme with what it is for` | `reorder readme around the argument` |

The pattern in the first column is a subject that wants to be quoted. A subject's whole
job is to tell somebody scanning `git log --oneline` whether this is the commit they are
looking for, and a slogan is worse at that than a description. The same instinct produces
a body made of five-word sentences, each landing like a conclusion, which is rule 10.

### Bad, and why

```
feat: Implement comprehensive and robust validation logic for the plan
loader module - this seamlessly handles all edge cases

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

Too long. Past tense marketing. Em dash. Claims coverage it cannot prove.
Attribution nobody needs.

```
validate plan against pack manifests
```

That is the same commit.

## Code

Same principle. Clarity first, volume last.

1. **No comment that restates the code.** `# increment counter` above `i += 1` gets
   deleted in review.
2. **Comment only what the code cannot say**: a why, a constraint, a reference to a
   spec or a paper, a known sharp edge.
3. **Docstrings on public functions only**, one line, saying what it returns. Skip the
   Args and Returns blocks unless the types are genuinely unclear.
4. **No defensive noise.** Do not catch an exception you cannot handle. Do not check
   for a condition the type system already rules out.
5. **Functions do one thing.** If you need a section comment inside a function, that
   section is a function.
6. **No abbreviations that need a glossary.** `manifest`, not `mfst`.
7. **Fail closed.** A missing file, an unresolvable digest or a stale hash is an error
   with a non-zero exit. Never a warning, never a silent default. This tool produces
   evidence, and evidence that degraded quietly is worse than no evidence.
8. **No country, language or regulator logic in `src/`.** All of it belongs in packs
   and in `mappings/`. CI fails the build on a two-letter country code in `src/`.
9. **`src/` type checks under `mypy --strict`.** The package ships `py.typed`, so the
   annotations are a promise to whoever imports it, not a note to the next reader.
   Where a value genuinely arrives untyped, from `json.loads` or `yaml.safe_load`,
   annotate it at that boundary rather than letting `Any` spread inward.
10. **`tests/` is deliberately not type checked**, and annotations there are welcome
   rather than required. A wrong fixture fails its own test on the next run, which is
   louder than a type error, so the checker would be a second opinion on the one thing
   already covered. The cost is a test helper drifting from the function it exercises,
   which is accepted. The reasoning is in `pyproject.toml` beside the `files` setting,
   so nobody has to infer it from a one line list.

### Bad

```python
def process_items(items: list[dict]) -> dict:
    """
    Process the items.

    Args:
        items: A list of items to process.

    Returns:
        A dictionary containing the processed results.
    """
    # Initialise the results dictionary
    results = {}
    # Loop over each item in the list
    for item in items:
        # Check if the item is valid
        if item is not None:
            results[item["id"]] = item
    return results
```

### Good

```python
def index_by_id(items: list[ItemRecord]) -> dict[str, ItemRecord]:
    """Index records by item_id. Raises on a duplicate."""
    out = {}
    for item in items:
        if item.item_id in out:
            raise DuplicateItemError(item.item_id)
        out[item.item_id] = item
    return out
```

Shorter, typed, named for what it does, and it fails closed on the case the first
version silently swallowed.

## Documentation

The README is the only document most people read. Optimise it for someone who has
five minutes and a system they want to test.

1. What it is, in two sentences.
2. What it needs to run.
3. A command that produces output.
4. Everything else in `docs/`.

No badges beyond build and licence. No feature list written as marketing. No emoji.

## Naming

The instrument is **Touchstone**. The index it computes is **DQI**.

- Tool versions: `Touchstone 1.0`.
- Specification versions: `DQI Specification v1.0`.
- Never `DQI 1.0` on its own. It is ambiguous and the ambiguity is permanent.

## Before you push

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/check_commit_msg.py .git/COMMIT_EDITMSG
uv run python scripts/check_dco.py .git/COMMIT_EDITMSG
```

`uv` is the only thing you need installed. It fetches the interpreter and the
dependencies itself, and CI runs these same four commands, so a green run here is a
green run there. Install it with `brew install uv` or from https://docs.astral.sh/uv/.

Install the hooks once and the last one runs itself:

```bash
git config core.hooksPath .githooks
```

## Branches and pull requests

`main` is protected. Work happens on a branch and arrives through a pull request, which
is also the only way the `commit-messages` job runs: it is skipped on a direct push, so a
branch that never becomes a pull request has never had its commit messages checked.

```bash
git switch -c add-egress-proxy
# ... commits ...
git push -u origin add-egress-proxy
gh pr create --fill
```

**Branch names** are the change, in the same voice as a commit subject: lowercase,
hyphenated, imperative. `add-egress-proxy`, `fix-swap-limit`, `drop-dqi-alias`. No
initials, no dates, no ticket numbers.

- One change per pull request.
- The description says what changed and why. Not how, the diff says how.
- A pull request that changes a contract in `src/touchstone/contracts/` is a major
  version and needs a note saying what breaks.
- Every commit in the pull request has to pass the message rules above, not just the
  last one. Fix an earlier one with `git rebase -i` before asking for a merge.

**Why protect `main` when one person is writing the code.** Because the checks that
matter most only run on a pull request, and because a repository whose whole subject is
evidence anyone can re-check should be able to show that its own changes were checked.
Admins can still push directly when something has to land; the protection makes the
reviewed path the default, not the only one.
