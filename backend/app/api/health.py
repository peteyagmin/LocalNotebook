from fastapi import APIRouter

from app.version import app_version

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": app_version()}
