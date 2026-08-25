class TouchstoneError(Exception):
    """Base for every error this tool raises."""


class PlanError(TouchstoneError):
    """The plan is malformed or references something that does not exist."""


class BundleError(TouchstoneError):
    """The bundle is malformed or its hashes do not match."""


class BackendError(TouchstoneError):
    """The runtime could not execute the pack. A pack that runs and exits non-zero is not
    this: that is a result, and it is reported in RunResult.exit_code."""
