import os
from fastapi import APIRouter, HTTPException
import stripe

router = APIRouter()

stripe.api_key = os.getenv('STRIPE_SECRET', '')

@router.post('/create-checkout-session')
def create_checkout_session(price_id: str = None):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail='Stripe not configured')
    price = price_id or os.getenv('STRIPE_PRICE_BASIC')
    try:
        session = stripe.checkout.Session.create(
            mode='subscription',
            line_items=[{'price': price, 'quantity': 1}],
            success_url='https://example.com/success',
            cancel_url='https://example.com/cancel',
        )
        return {'id': session.id, 'url': session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
