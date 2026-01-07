
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from .forms import NewAuditForm, RegisterForm


def index_view(request):
    return render(request, 'index.html')

@login_required
def dashboard_view(request):
    ctx = {
        'open_audits_count': 12,
        'recent_activity': [
            {'title': 'Audit A updated', 'date': '2026-01-06'},
            {'title': 'Audit B created', 'date': '2026-01-05'},
        ],
    }
    return render(request, 'dashboard.html', ctx)

@login_required
def new_audit_view(request):
    form = NewAuditForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        # TODO: Persist new audit
        return redirect('dashboard')
    return render(request, 'new_audit.html', {'form': form})

@login_required
def admin_view(request):
    return render(request, 'admin.html')

@login_required
def verify_view(request):
    token_sent = True
    email = request.user.email or 'user@example.com'
    if request.method == 'POST':
        # TODO: verify code
        return redirect('dashboard')
    return render(request, 'verify.html', {'token_sent': token_sent, 'email': email})

# Public detail (no login)
def audit_detail_open_view(request):
    audit = {
        'title': 'Public Audit',
        'status': 'Open',
        'public_summary': 'Summary available to the public.',
    }
    return render(request, 'audit_detail_open.html', {'audit': audit})

@login_required
def audit_detail_view(request):
    audit = {
        'title': 'Internal Audit',
        'status': 'Open',
        'is_open': True,
        'owner': request.user.username,
        'created_at': '2026-01-06',
        'findings': [
            {'title': 'Policy gap', 'description': 'Missing retention policy.'},
            {'title': 'Access control', 'description': 'Role misalignment detected.'}
        ]
    }
    return render(request, 'audit_detail.html', {'audit': audit})

# Auth

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')
