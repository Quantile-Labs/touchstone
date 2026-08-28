# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0

__version__ = "0.3.0"
"""The version this build stamps into every bundle, estimate and score card.

It is a literal rather than a lookup through `importlib.metadata`, so it holds when the
package is run from a checkout that was never installed. `tests/test_version.py` pins it to
`pyproject.toml`, because 0.1.0 shipped with this line still reading `0.0.1` and every
artefact it sealed claims a version that was never released.
"""
