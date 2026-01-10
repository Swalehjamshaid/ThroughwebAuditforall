
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Audit

class LoginForm(AuthenticationForm):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "Username", "class": "form-control"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"placeholder": "Password", "class": "form-control"}))

class RegisterForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

class NewAuditForm(forms.ModelForm):
    class Meta:
        model = Audit
        fields = ["title", "description", "public_summary"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "public_summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

class VerifyForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter code"}))
