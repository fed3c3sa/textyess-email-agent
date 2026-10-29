"""Turn the email into a complete HTML document, ready to send.

This is only the envelope. Layout, colors and styles are all in the sections the
model wrote. The subject becomes the title, the preheader becomes hidden text that
email apps show in the inbox list, and the other sections follow in order inside a
centered column 600px wide: the standard frame of an HTML email.
"""

import html

from app.schemas.email import Email

PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{subject}</title>
</head>
<body style="margin:0; padding:0;">
<div style="display:none; max-height:0; overflow:hidden;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:600px;"><tr><td>
{body}
</td></tr></table>
</td></tr></table>
</body>
</html>
"""


def render_email(email: Email) -> str:
    """The email as a complete HTML document."""
    text = {section.id: section.content for section in email.sections}
    body = "\n".join(s.content for s in email.sections if s.id not in ("subject", "preheader"))
    return PAGE.format(
        subject=html.escape(text.get("subject", "")),
        preheader=html.escape(text.get("preheader", "")),
        body=body,
    )
