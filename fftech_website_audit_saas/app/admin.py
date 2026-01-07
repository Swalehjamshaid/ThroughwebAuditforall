
from django.contrib import admin
from .models import Audit, Finding

@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "created_at")
    search_fields = ("title", "owner__username")
    list_filter = ("status", "created_at")

@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("audit", "title")
    search_fields = ("audit__title", "title")
