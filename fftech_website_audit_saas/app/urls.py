
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('audits/new/', views.new_audit_view, name='new_audit'),
    path('audits/detail/', views.audit_detail_view, name='audit_detail'),
    path('public/audit/', views.audit_detail_open_view, name='audit_detail_open'),
    path('admin-panel/', views.admin_view, name='admin'),
    path('verify/', views.verify_view, name='verify'),

    # Auth
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
