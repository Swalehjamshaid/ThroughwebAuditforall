
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string
from django.conf import settings
from .tokens import account_activation_token

# Sends a verification email containing a unique activation link.
def send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)
    activation_url = request.build_absolute_uri(
        reverse('verify_link', kwargs={'uidb64': uid, 'token': token})
    )
    subject = 'Verify your account'
    context = {
        'user': user,
        'activation_url': activation_url,
        'site_name': getattr(settings, 'SITE_NAME', 'AuditApp')
    }
    text_body = render_to_string('emails/activation.txt', context)
    html_body = render_to_string('emails/activation.html', context)

    email = EmailMultiAlternatives(subject, text_body, to=[user.email])
    email.attach_alternative(html_body, 'text/html')
    email.send()
