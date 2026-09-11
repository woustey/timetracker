"""Domain exceptions. Everything raised on purpose derives from ``TimeTrackerError``."""

from __future__ import annotations


class TimeTrackerError(Exception):
    """Base class for all deliberate application errors."""


class NotFoundError(TimeTrackerError):
    """A record addressed by id/uuid does not exist."""


class SchemaTooNewError(TimeTrackerError):
    """The database was written by a newer version of the application (PRD-02 §4.3)."""

    def __init__(self, db_version: int, code_version: int) -> None:
        super().__init__(
            f"Database schema is version {db_version}; this build understands up to "
            f"{code_version}. Refusing to open it rather than risk corrupting your data."
        )
        self.db_version = db_version
        self.code_version = code_version


class DuplicateLabelError(TimeTrackerError):
    """A label with the same normalised name already exists in that dimension (FR-402)."""


class LabelInUseError(TimeTrackerError):
    """A label referenced by entries cannot be hard-deleted (FR-405)."""


class ValidationError(TimeTrackerError):
    """A value violates a domain rule (negative duration, empty label name, ...)."""
