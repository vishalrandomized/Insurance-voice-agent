from fastapi import APIRouter

from .callbacks import router as callbacks_router
from .documents import router as documents_router
from .health import router as health_router
from .leads import router as leads_router
from .sessions import router as sessions_router

router = APIRouter()
router.include_router(health_router)
router.include_router(sessions_router)
router.include_router(leads_router)
router.include_router(callbacks_router)
router.include_router(documents_router)
