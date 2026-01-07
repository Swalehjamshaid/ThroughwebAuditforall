
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

from .forms import RegisterForm, NewAuditForm
from .models import Audit
from .tokens import account_activation_token
from .email_utils import send_verification_email

User = get_user_model()

def index_view(request):
    return render(request, 'index.html')

@login_required
def dashboard_view(request):
    ctx = {
        'open_audits_count': Audit.objects.filter(is_open=True).count(),
        'recent_activity': [
            {'title': a.title, 'date': a.created_at} for a in Audit.objects.all()[:5]
        ],
    }
    return render(request, 'dashboard.html', ctx)

@login_required
def new_audit_view(request):
    if request.method == 'POST':
        form = NewAuditForm(request.POST)
        if form.is_valid():
            audit = form.save(commit=False)
            audit.owner = request.user
            audit.save()
            messages.success(request, 'Audit created successfully.')
            return redirect('dashboard')
    else:
        form = NewAuditForm()
    return render(request, 'new_audit.html', {'form': form})

@user_passes_test(lambda u: u.is_staff)
@login_required
def admin_view(request):
    return render(request, 'admin.html')

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not user.is_active:
                messages.error(request, 'Please verify your email to activate your account.')
                return redirect('login')
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm(request)
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('index')

def register_view(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            send_verification_email(request, user)
            return render(request, 'verify.html', {
                'token_sent': True,
                'email': user.email,
            })
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})

def verify_link_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        messages.success(request, 'Your account has been activated and you are now logged in.')
        return render(request, 'verify.html', {
            'token_sent': False,
            'email': user.email,
        })
    else:
        messages.error(request, 'Activation link is invalid or has expired.')
        return render(request, 'verify.html', {
            'token_sent': False,
            'email': None,
        })
