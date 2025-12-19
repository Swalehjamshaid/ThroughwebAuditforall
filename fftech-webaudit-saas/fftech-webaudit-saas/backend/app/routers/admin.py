from fastapi import APIRouter

router = APIRouter()

@router.get('/users')
def list_users():
    # Placeholder
    return [{"email": "admin@example.com", "role": "admin"}]

@router.get('/metrics')
def system_metrics():
    return {"uptime": "ok", "audits": 0}
