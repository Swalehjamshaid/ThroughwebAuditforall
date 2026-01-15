from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import jwt

from .config import settings
from .db import db_session           # ← FIXED: use this import
from .models import MagicToken, User
from .email_utils import send_email

router = APIRouter(prefix='/auth', tags=['auth'])

# ... rest of your code remains exactly the same
