# main.py — FF Tech Elite World-Class Website Audit SaaS (Updated with $5/mo Subscription + Free Trial)
# Added: Stripe integration for $5/month plan
# Free Trial: No registration required — instant access to basic audit (limited features)
# Paid ($5/mo): Full features after Stripe Checkout
# Core Difference Logic: Free = limited audits/metrics/scheduling | Paid = unlimited + full reports + scheduling
# ------------------------------------------------------------------------------

import os
import json
import secrets
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
from zoneinfo import ZoneInfo

import httpx
import pdfkit
import openai
import stripe  # pip install stripe
from bs4 import BeautifulSoup
from fastapi import FastAPI, Form, Request, Depends, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase, Session
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from email_validator import validate_email, EmailNotValidError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import smtplib

# ------------------------------------------------------------------------------
# Stripe Configuration
# ------------------------------------------------------------------------------
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
PRICE_ID = os.getenv("PRICE_ID")  # Your $5/month recurring price ID from Stripe Dashboard

# ------------------------------------------------------------------------------
# Other Configuration (same as before)
# ------------------------------------------------------------------------------
APP_NAME = "FF Tech — Elite AI Website Audit"
APP_DOMAIN = os.getenv("APP_DOMAIN", "http://localhost:8000")
# ... (rest same)

# ------------------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------------------
app = FastAPI(title=APP_NAME)

templates = Jinja2Templates(directory="templates")

# ------------------------------------------------------------------------------
# User Model Additions for Subscription
# ------------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    # ... existing fields ...
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    is_paid = Column(Boolean, default=False)  # True if active $5/mo subscription
    trial_used = Column(Boolean, default=False)  # Prevent multiple free trials

# ------------------------------------------------------------------------------
# Core Difference Logic
# ------------------------------------------------------------------------------
def is_full_access(user: Optional[User]) -> bool:
    """Free trial or registered free user = limited | Paid subscription = full"""
    if not user:
        return False  # Guest free trial: limited
    return user.is_paid  # Paid users get full access

def check_access(user: Optional[User], feature: str):
    """Raise error if user doesn't have access to premium feature"""
    if not is_full_access(user):
        allowed_free = ["basic_audit", "view_summary"]  # Define free features
        if feature not in allowed_free:
            raise HTTPException(status_code=403, detail="Upgrade to $5/mo for full access")

# Example usage in routes:
# check_access(user, "full_report_pdf")
# check_access(user, "schedule_daily")
# check_access(user, "competitor_analysis")

# ------------------------------------------------------------------------------
# Free Trial (No Registration Required)
# ------------------------------------------------------------------------------
@app.post("/trial/audit")
async def free_trial_audit(url: str = Form(...)):
    """Guest user — instant basic audit (limited metrics, no PDF, no scheduling)"""
    # Run limited audit (e.g., only 20 metrics, no competitor)
    limited_result = compute_audit(url)  # Your audit function with limits for free
    limited_result["limited"] = True
    limited_result["message"] = "Free trial audit — Upgrade for full report & scheduling"
    return JSONResponse(limited_result)

# ------------------------------------------------------------------------------
# Paid Subscription Routes ($5/month)
# ------------------------------------------------------------------------------
@app.post("/create-checkout-session")
async def create_checkout(request: Request, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Login required for subscription")
    
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email)
        user.stripe_customer_id = customer.id
        db = SessionLocal()
        db.add(user)
        db.commit()
        db.close()

    try:
        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=APP_DOMAIN + "/dashboard?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=APP_DOMAIN + "/pricing",
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        db = SessionLocal()
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.stripe_subscription_id = subscription_id
            user.is_paid = True
            db.commit()
        db.close()

    elif event['type'] == 'invoice.payment_failed':
        # Optional: downgrade user
        pass

    return {"status": "success"}

# ------------------------------------------------------------------------------
# Pricing / Upgrade Page
# ------------------------------------------------------------------------------
@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, user: Optional[User] = Depends(get_current_user)):
    return templates.TemplateResponse("pricing.html", {
        "request": request,
        "user": user,
        "is_paid": user.is_paid if user else False
    })

# ------------------------------------------------------------------------------
# Enhanced Audit Route with Access Control
# ------------------------------------------------------------------------------
@app.post("/audit/run")
async def run_audit(data: Dict, user: Optional[User] = Depends(get_current_user)):
    # Free trial (no login): limited
    if not user:
        # Limit to basic metrics only
        return limited_audit(data["url"])
    
    # Registered free: some limits
    if not user.is_paid:
        check_access(user, "full_audit")
    
    # Paid: full access
    return full_audit(data["url"], data.get("competitor_url"))

# ------------------------------------------------------------------------------
# Rest of your code remains the same
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
