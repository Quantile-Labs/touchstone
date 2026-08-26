# Golden bundles

A frozen bundle and the estimates computed from it, byte-compared by
`tests/test_golden_bundle.py` so that a change in how `estimates.json` serialises cannot
pass unnoticed. The unit tests in `tests/test_stats_*.py` pin the arithmetic; this pins
what a client re-checking an old bundle actually reads off the disk.

`run-001/items.jsonl` is the input and is **never regenerated**. It is a hand-built sample
covering the paths that serialise differently: two packs, so the pooled figures sit beside
the per-pack ones, a boolean outcome and a continuous score, so both estimators appear,
confidences, so there is a calibration curve, and two replicates, so there is
between-replicate variance. Rewriting it would let the input drift while the comparison
carried on passing.

`run-001.json` records the `estimate()` call that produced the frozen numbers. The test
and the regenerator both read it, so neither can drift from the other.

## Regenerating

Only after a change that is meant to move the numbers or the layout. The diff is the
review: an unexplained line in it is the bug this directory exists to catch.

```bash
uv run python scripts/make_golden_bundle.py
```

`sealed_utc` in `MANIFEST.json` moves every time and the bundle hash does not, because
that hash is over the file list alone.
