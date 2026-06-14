class RepositoryError(RuntimeError):
    """Base error raised by persistence and service operations."""


class NotFoundError(RepositoryError):
    pass


class ConflictError(RepositoryError):
    pass


class ValidationError(RepositoryError):
    pass


class PersistenceError(RepositoryError):
    pass
