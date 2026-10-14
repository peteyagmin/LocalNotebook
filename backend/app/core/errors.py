from __future__ import annotations


class AppError(Exception):
    """An error with an HTTP status and a user-readable message (spec §11.2)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
