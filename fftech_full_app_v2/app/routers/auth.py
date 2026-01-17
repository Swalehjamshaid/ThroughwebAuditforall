
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])

@router.get("/health")
async def health():
    return {"status": "ok"}
