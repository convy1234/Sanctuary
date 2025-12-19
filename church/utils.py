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



# utils.py - Replace your render_to_pdf function
from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
import os

def render_to_pdf(template_src, context_dict={}):
    """
    Renders a Django template to a PDF file using WeasyPrint.
    Returns an HttpResponse object with the PDF.
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        
        template = get_template(template_src)
        html = template.render(context_dict)
        
        # Create PDF with WeasyPrint
        result = BytesIO()
        
        # You can add custom CSS files here if needed
        html_obj = HTML(string=html, base_url=settings.BASE_DIR)
        
        # Generate PDF
        html_obj.write_pdf(result)
        
        return HttpResponse(result.getvalue(), content_type='application/pdf')
        
    except ImportError:
        return HttpResponse(
            "WeasyPrint is not installed. Install with: pip install weasyprint",
            status=500
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return HttpResponse(
            f"PDF generation failed: {str(e)}<br><br>Details:<pre>{error_details}</pre>",
            status=500
        )