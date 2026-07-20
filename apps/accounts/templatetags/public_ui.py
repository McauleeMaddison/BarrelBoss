import re

from django import template


register = template.Library()

DEMO_PREVIEW_MARKER = "[DEMO_PREVIEW]"
MULTISPACE_RE = re.compile(r"[ \t]{2,}")


@register.filter
def public_note(value):
    text = str(value or "").replace(DEMO_PREVIEW_MARKER, "").strip()
    if not text:
        return ""
    return MULTISPACE_RE.sub(" ", text)

