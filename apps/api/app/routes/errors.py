from fastapi import HTTPException

from app.db.errors import (
    ConflictError,
    NotFoundError,
    PersistenceError,
    ValidationError,
)


def as_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(exc)},
        )
    if isinstance(exc, ConflictError):
        return HTTPException(
            status_code=409,
            detail={"code": "conflict", "message": str(exc)},
        )
    if isinstance(exc, ValidationError):
        return HTTPException(
            status_code=422,
            detail={"code": "invalid_request", "message": str(exc)},
        )
    if isinstance(exc, PersistenceError):
        return HTTPException(
            status_code=503,
            detail={
                "code": "persistence_unavailable",
                "message": "Persistence service is unavailable",
            },
        )
    return HTTPException(
        status_code=500,
        detail={"code": "internal_error", "message": "Unexpected server error"},
    )
