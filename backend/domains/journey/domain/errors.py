from __future__ import annotations


class JourneyDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class JourneyValidationError(JourneyDomainError):
    pass


class JourneyForbiddenError(JourneyDomainError):
    pass


class JourneyNotFoundError(JourneyDomainError):
    pass


class JourneyConflictError(JourneyDomainError):
    pass
