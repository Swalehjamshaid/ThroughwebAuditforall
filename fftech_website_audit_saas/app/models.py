
from django.conf import settings
from django.db import models

class Audit(models.Model):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='audits')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Open')
    public_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status == 'Open'

class Finding(models.Model):
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE, related_name='findings')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.audit.title} - {self.title}"
