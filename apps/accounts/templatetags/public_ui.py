import re

from django import template


register = template.Library()

DEMO_PREVIEW_MARKER = "[DEMO_PREVIEW]"
MULTISPACE_RE = re.compile(r"[ \t]{2,}")
USERNAME_SPLIT_RE = re.compile(r"[_\-.]+")


@register.filter
def public_note(value):
    text = str(value or "").replace(DEMO_PREVIEW_MARKER, "").strip()
    if not text:
        return ""
    return MULTISPACE_RE.sub(" ", text)


@register.filter
def display_name(value):
    if hasattr(value, "get_full_name") and hasattr(value, "get_username"):
        full_name = value.get_full_name().strip()
        if full_name:
            return full_name
        text = value.get_username()
    else:
        text = str(value or "").strip()

    if not text:
        return ""

    normalized = USERNAME_SPLIT_RE.sub(" ", text).strip()
    if not normalized:
        return ""

    if normalized == normalized.lower():
        return normalized.title()
    return normalized
