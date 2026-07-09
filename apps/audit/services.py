from apps.accounts.permissions import get_user_role

from .models import AuditEvent


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_audit_event(
    request,
    *,
    action,
    summary,
    target=None,
    details=None,
):
    try:
        actor = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        actor_role = get_user_role(actor, request=request) if actor else None
        target_model = target._meta.label_lower if target is not None else ""
        target_id = str(target.pk) if target is not None and target.pk is not None else ""
        venue = getattr(request, "active_venue", None)
        if venue is None and target is not None:
            venue = getattr(target, "venue", None)
            if venue is None and hasattr(target, "order"):
                venue = getattr(target.order, "venue", None)

        return AuditEvent.objects.create(
            venue=venue,
            actor=actor,
            actor_username=actor.get_username() if actor else "anonymous",
            actor_role=actor_role or "",
            action=action,
            target_model=target_model,
            target_id=target_id,
            summary=summary,
            details=details or {},
            request_path=request.get_full_path()[:255],
            ip_address=_client_ip(request),
        )
    except Exception:
        # Audit logging should not block core business actions.
        return None
