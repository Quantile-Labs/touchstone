class TouchstoneError(Exception):
    """Base for every error this tool raises."""


class PlanError(TouchstoneError):
    """The plan is malformed or references something that does not exist."""


class BundleError(TouchstoneError):
    """The bundle is malformed or its hashes do not match."""
