
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('audits/new/', views.new_audit_view, name='new_audit'),
    path('admin-panel/', views.admin_view, name='admin'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('verify/<uidb64>/<token>/', views.verify_link_view, name='verify_link'),
]
