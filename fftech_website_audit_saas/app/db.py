from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt
from .config import settings
from .database import db_session           # ← ONLY THIS LINE CHANGED
from .models import MagicToken, User
from .email_utils import send_email

router = APIRouter(prefix='/auth', tags=['auth'])

# ... rest of the file stays exactly the same
