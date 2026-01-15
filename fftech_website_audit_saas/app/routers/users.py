from fastapi import APIRouter
router = APIRouter()
@router.get('/users/me')
async def me():
    return {"email": "demo@example.com", "subscription": "free"}