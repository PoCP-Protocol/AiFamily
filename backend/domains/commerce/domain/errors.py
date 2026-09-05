class CommerceDomainError(Exception):
    """Base exception translated by the commerce HTTP adapter."""


class CommerceValidationError(CommerceDomainError):
    pass


class CommerceNotFoundError(CommerceDomainError):
    pass


class CommerceConflictError(CommerceDomainError):
    pass
