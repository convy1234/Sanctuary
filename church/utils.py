from django.core.mail import send_mail
from django.urls import reverse


def send_invitation_email(invitation, request=None):
    """Send an invitation email with the acceptance link and token."""
    accept_path = reverse("accept_invite")
    accept_url = (
        request.build_absolute_uri(f"{accept_path}?token={invitation.token}")
        if request
        else f"{accept_path}?token={invitation.token}"
    )
    subject = "You're invited to join {org}".format(org=invitation.organization.name)
    message = (
        f"You have been invited to join {invitation.organization.name}.\n\n"
        f"Use this link to accept: {accept_url}\n"
        f"Or use the token directly: {invitation.token}\n"
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[invitation.email],
            fail_silently=True,
        )
    except Exception:
        # Ignore email failures to keep invitation creation non-blocking.
        pass
