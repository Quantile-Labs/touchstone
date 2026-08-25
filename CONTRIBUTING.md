# Contributing

Read this before your first commit. The rules here are enforced by CI, not by review.

## Commit messages

Write like an engineer with work to do. Short, factual, imperative.

```
add wilson interval to rate estimator
fix digest resolution for multi-arch images
drop unused seed parameter from plan loader
```

**Rules, all enforced by `scripts/check_commit_msg.py`:**

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

**Why 50 characters.** `git log --oneline` is how the history gets read. A subject
that wraps is a subject nobody reads.

**Why the adjective list.** Those words carry no information about the change. If a
commit needs to say the work is good, the work is not good enough.

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
uv run pytest
uv run python scripts/check_commit_msg.py .git/COMMIT_EDITMSG
```

`uv` is the only thing you need installed. It fetches the interpreter and the
dependencies itself, and CI runs these same four commands, so a green run here is a
green run there. Install it with `brew install uv` or from https://docs.astral.sh/uv/.

Install the hooks once and the last one runs itself:

```bash
git config core.hooksPath .githooks
```

## Pull requests

- One change per pull request.
- The description says what changed and why. Not how, the diff says how.
- A pull request that changes a contract in `src/touchstone/contracts/` is a major
  version and needs a note saying what breaks.
