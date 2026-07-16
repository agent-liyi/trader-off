"""Tests for custom exceptions."""

from trader_off.utils.exceptions import (
    InsufficientDataError,
    ModelVersionExistsError,
    PathTraversalError,
    VisualizationDependencyError,
    FeatureNameMismatchError,
)


class TestExceptions:
    """Unit tests for custom exception classes."""

    def test_exceptions_are_exception_subclasses(self):
        """All custom exceptions should inherit from Exception."""
        exceptions = [
            InsufficientDataError,
            ModelVersionExistsError,
            PathTraversalError,
            VisualizationDependencyError,
            FeatureNameMismatchError,
        ]
        for exc in exceptions:
            assert issubclass(exc, Exception), f"{exc.__name__} not a subclass of Exception"

    def test_exceptions_can_be_raised_and_caught(self):
        """Each exception can be raised and caught with pytest.raises."""
        test_cases = [
            (InsufficientDataError, "need at least 30 days"),
            (ModelVersionExistsError, "version already exists"),
            (PathTraversalError, "path traversal detected"),
            (VisualizationDependencyError, "matplotlib is required"),
            (FeatureNameMismatchError, "feature names mismatch"),
        ]
        for exc_cls, msg in test_cases:
            with pytest.raises(exc_cls, match=msg):
                raise exc_cls(msg)


import pytest
