"""Custom exceptions for trader-off."""


class InsufficientDataError(Exception):
    """Raised when there is not enough data to compute a metric."""

    pass


class ModelVersionExistsError(Exception):
    """Raised when attempting to save a model to an existing version directory."""

    pass


class PathTraversalError(Exception):
    """Raised when a file path escapes its allowed root directory."""

    pass


class VisualizationDependencyError(Exception):
    """Raised when matplotlib is required but not installed."""

    pass


class FeatureNameMismatchError(Exception):
    """Raised when feature names at inference time do not match training time."""

    pass
