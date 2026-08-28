# SPDX-FileCopyrightText: 2026 Quantile Labs
# SPDX-License-Identifier: Apache-2.0


class TouchstoneError(Exception):
    """Base for every error this tool raises."""


class PlanError(TouchstoneError):
    """The plan is malformed or references something that does not exist."""


class BundleError(TouchstoneError):
    """The bundle is malformed or its hashes do not match."""


class AnchorError(TouchstoneError):
    """The plan hash could not be timestamped."""


class BackendError(TouchstoneError):
    """The runtime could not execute the pack. A pack that runs and exits non-zero is not
    this: that is a result, and it is reported in RunResult.exit_code."""


class EstimateError(TouchstoneError):
    """The item records could not be read, or could not support the estimate asked for."""


class ScoreCardError(TouchstoneError):
    """The score card is malformed, names something the bundle does not hold, or asks for
    a condition the evidence cannot answer."""
