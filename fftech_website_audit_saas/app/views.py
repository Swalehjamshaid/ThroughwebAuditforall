
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import LoginForm, RegisterForm, NewAuditForm, VerifyForm
from .models import Audit


def index_view(request):
    return render(request, 'index.html')


def dashboard_view(request):
    open_audits_count = Audit.objects.filter(status='Open').count()
    recent_activity = [
        {"title": a.title, "date": a.created_at} for a in Audit.objects.all()[:5]
    ]
    ctx = {
        'open_audits_count': open_audits_count,
        'recent_activity': recent_activity,
    }
    return render(request, 'dashboard.html', ctx)


@login_required
def new_audit_view(request):
    if request.method == 'POST':
        form = NewAuditForm(request.POST)
        if form.is_valid():
            audit = form.save(commit=False)
            audit.owner = request.user
            audit.status = 'Open'
            audit.save()
            messages.success(request, 'Audit created successfully.')
            return redirect('dashboard')
    else:
        form = NewAuditForm()
    return render(request, 'new_audit.html', {'form': form})


def audit_detail_view(request, pk: int):
    audit = get_object_or_404(Audit, pk=pk)
    return render(request, 'audit_detail.html', {'audit': audit})


def audit_detail_open_view(request, pk: int):
    audit = get_object_or_404(Audit, pk=pk)
    return render(request, 'audit_detail_open.html', {'audit': audit})


def admin_view(request):
    return render(request, 'admin.html')


def verify_view(request):
    email = request.user.email if request.user.is_authenticated else ''
    token_sent = False
    if request.method == 'POST':
        form = VerifyForm(request.POST)
        if form.is_valid():
            messages.success(request, 'Verification successful.')
            token_sent = True
            return redirect('dashboard')
    else:
        form = VerifyForm()
    return render(request, 'verify.html', {'form': form, 'email': email, 'token_sent': token_sent})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials.')
    else:
        form = LoginForm(request)
    return render(request, 'login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = RegisterForm()
    return render(request, 'register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')
