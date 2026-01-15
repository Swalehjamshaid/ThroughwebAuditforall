from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
from .config import settings
from .database import db_session           # ← FIXED: use db_session (this is the correct name)
from .models import MagicToken, User
from .email_utils import send_email

router = APIRouter(prefix='/auth', tags=['auth'])

class LoginRequest(BaseModel):
    email: EmailStr

@router.post('/login-link')
def send_login_link(payload: LoginRequest, request: Request, db: Session = Depends(db_session)):
    # ... (rest of the function remains unchanged)

@router.get('/callback')
def magic_callback(token: str, db: Session = Depends(db_session)):
    # ... (rest of the function remains unchanged)
