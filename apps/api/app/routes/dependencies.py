from app.db import Repository, get_repository
from app.services.callbacks import CallbackService
from app.services.leads import LeadService
from app.services.sessions import SessionService


def repository_dependency() -> Repository:
    return get_repository()


def lead_service_dependency() -> LeadService:
    return LeadService(repository_dependency())


def callback_service_dependency() -> CallbackService:
    return CallbackService(repository_dependency())


def session_service_dependency() -> SessionService:
    return SessionService(repository_dependency())
