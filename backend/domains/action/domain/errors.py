"""Action domain errors exposed to application and HTTP adapters."""


class ActionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ActionValidationError(ActionError):
    pass


class ActionForbiddenError(ActionError):
    pass


class ActionNotFoundError(ActionError):
    pass


class ActionConflictError(ActionError):
    pass


__all__ = [
    "ActionConflictError",
    "ActionError",
    "ActionForbiddenError",
    "ActionNotFoundError",
    "ActionValidationError",
]
