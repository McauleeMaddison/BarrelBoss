from django.urls import reverse

from .permissions import is_management, role_home_name


ROUTE_GROUPS = {
    "home": {
        "dashboard:home",
        "dashboard:management_portal",
        "dashboard:staff_portal",
    },
    "stock": {
        "stock:list",
        "stock:add",
        "stock:edit",
        "stock:delete",
    },
    "orders": {
        "orders:list",
        "orders:add",
        "orders:edit",
        "orders:status",
    },
    "checklists": {
        "checklists:list",
        "checklists:add",
        "checklists:edit",
        "checklists:toggle",
        "checklists:delete",
    },
    "shifts": {
        "shifts:list",
        "shifts:add",
        "shifts:edit",
        "shifts:delete",
    },
    "breakages": {
        "breakages:list",
        "breakages:add",
        "breakages:delete",
    },
    "sales": {
        "sales:list",
        "sales:add",
        "sales:edit",
        "sales:sync_center",
        "sales:run_due_syncs",
        "sales:integration_add",
        "sales:integration_edit",
        "sales:integration_run",
        "sales:mapping_add",
    },
    "suppliers": {
        "suppliers:list",
        "suppliers:add",
        "suppliers:edit",
        "suppliers:delete",
    },
    "staff": {
        "staff",
        "staff_add",
        "staff_edit",
        "staff_toggle_active",
    },
    "reports": {
        "reports",
    },
    "audit": {
        "audit:list",
    },
    "settings": {
        "settings",
        "push_subscribe",
        "push_unsubscribe",
    },
}


def _group_active(current, *group_names):
    return any(current in ROUTE_GROUPS[group_name] for group_name in group_names)


def _build_url(url_name, *, query=None):
    url = reverse(url_name)
    if query:
        return f"{url}?{query}"
    return url


def _nav_item(
    current,
    *,
    label,
    url_name,
    group,
    query=None,
    description="",
):
    return {
        "label": label,
        "url": _build_url(url_name, query=query),
        "active": _group_active(current, group),
        "description": description,
    }


def _action_item(*, label, url_name, copy, query=None, emphasis="default"):
    return {
        "label": label,
        "url": _build_url(url_name, query=query),
        "copy": copy,
        "emphasis": emphasis,
    }


def build_workspace_navigation(request):
    current = getattr(getattr(request, "resolver_match", None), "view_name", "")
    management_view = is_management(request.user, request=request)
    home_url_name = role_home_name(request.user, request=request)

    if management_view:
        primary_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Control board",
            ),
            _nav_item(
                current,
                label="Stock",
                url_name="stock:list",
                group="stock",
                description="Cellar and back bar",
            ),
            _nav_item(
                current,
                label="Orders",
                url_name="orders:list",
                group="orders",
                description="Approvals and deliveries",
            ),
            _nav_item(
                current,
                label="Tasks",
                url_name="checklists:list",
                group="checklists",
                description="Standards and checks",
            ),
            _nav_item(
                current,
                label="Rota",
                url_name="shifts:list",
                group="shifts",
                description="Coverage and hours",
            ),
        ]
        secondary_links = [
            _nav_item(
                current,
                label="Breakages",
                url_name="breakages:list",
                group="breakages",
                description="Loss log",
            ),
            _nav_item(
                current,
                label="Sales",
                url_name="sales:list",
                group="sales",
                description="Trade pulse",
            ),
            _nav_item(
                current,
                label="Suppliers",
                url_name="suppliers:list",
                group="suppliers",
                description="Partners and contacts",
            ),
            _nav_item(
                current,
                label="Staff",
                url_name="staff",
                group="staff",
                description="People and access",
            ),
            _nav_item(
                current,
                label="Reports",
                url_name="reports",
                group="reports",
                description="Downloadable summaries",
            ),
            _nav_item(
                current,
                label="Activity",
                url_name="audit:list",
                group="audit",
                description="Audit trail",
            ),
            _nav_item(
                current,
                label="Settings",
                url_name="settings",
                group="settings",
                description="Venue setup",
            ),
        ]
        quick_actions = [
            _action_item(
                label="Today sign-off",
                url_name="checklists:list",
                query="preset=today&status=pending",
                copy="Jump straight into the tasks that should close before the day rolls over.",
                emphasis="primary",
            ),
            _action_item(
                label="Count queue",
                url_name="stock:list",
                query="focus=uncounted",
                copy="Work through cellar lines that still need a fresh stock count.",
            ),
            _action_item(
                label="Pending deliveries",
                url_name="orders:list",
                query="preset=pending",
                copy="Track what is in transit before the cellar starts making assumptions.",
            ),
            _action_item(
                label="Create order",
                url_name="orders:add",
                copy="Raise a new supplier order once the live blockers are under control.",
            ),
        ]
        bar_title = "Management workspace"
        bar_copy = "Keep sign-off, cellar counts, and supplier follow-up one jump away."
        command_title = "Management actions"
        command_copy = "Use fast actions to close tasks, clear stock risk, and keep deliveries moving."
        mobile_dock_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Control board",
            ),
            _nav_item(
                current,
                label="Sign-off",
                url_name="checklists:list",
                group="checklists",
                query="preset=today&status=pending",
                description="Due now",
            ),
            _nav_item(
                current,
                label="Cellar",
                url_name="stock:list",
                group="stock",
                query="focus=cellar",
                description="Counts & gaps",
            ),
            _nav_item(
                current,
                label="Deliveries",
                url_name="orders:list",
                group="orders",
                query="preset=pending",
                description="In transit",
            ),
        ]
    else:
        primary_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Your shift board",
            ),
            _nav_item(
                current,
                label="Tasks",
                url_name="checklists:list",
                group="checklists",
                description="Assigned work",
            ),
            _nav_item(
                current,
                label="Stock",
                url_name="stock:list",
                group="stock",
                description="Live availability",
            ),
            _nav_item(
                current,
                label="Rota",
                url_name="shifts:list",
                group="shifts",
                description="Upcoming shifts",
            ),
            _nav_item(
                current,
                label="Requests",
                url_name="orders:list",
                group="orders",
                description="Submitted issues",
            ),
        ]
        secondary_links = [
            _nav_item(
                current,
                label="Report breakage",
                url_name="breakages:add",
                group="breakages",
                description="Send a loss report",
            ),
            _nav_item(
                current,
                label="Request stock",
                url_name="orders:add",
                group="orders",
                description="Raise a stock request",
            ),
        ]
        quick_actions = [
            _action_item(
                label="Open today tasks",
                url_name="checklists:list",
                query="preset=today&status=pending",
                copy="Jump straight into the tasks due in the current shift window.",
                emphasis="primary",
            ),
            _action_item(
                label="Service stock",
                url_name="stock:list",
                query="focus=service",
                copy="Check glassware, cleaning, and support lines before service gets busy.",
            ),
            _action_item(
                label="Request stock",
                url_name="orders:add",
                copy="Send a stock request to management before service slips.",
            ),
            _action_item(
                label="Report breakage",
                url_name="breakages:add",
                copy="Log spillages or breakages before handover loses the detail.",
            ),
        ]
        bar_title = "Shift workspace"
        bar_copy = "Surface the tasks, stock, and handover actions bar staff need most."
        command_title = "Shift actions"
        command_copy = "Use fast actions for the updates management needs from the floor."
        mobile_dock_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Shift board",
            ),
            _nav_item(
                current,
                label="Tasks",
                url_name="checklists:list",
                group="checklists",
                query="status=pending",
                description="My queue",
            ),
            _nav_item(
                current,
                label="Service",
                url_name="stock:list",
                group="stock",
                query="focus=service",
                description="Bar support",
            ),
            _nav_item(
                current,
                label="Requests",
                url_name="orders:list",
                group="orders",
                description="My orders",
            ),
        ]

    active_label = next(
        (link["label"] for link in [*primary_links, *secondary_links] if link["active"]),
        "Workspace",
    )

    return {
        "workspace_primary_links": primary_links,
        "workspace_secondary_links": secondary_links,
        "workspace_quick_actions": quick_actions,
        "workspace_bar_title": bar_title,
        "workspace_bar_copy": bar_copy,
        "workspace_active_label": active_label,
        "mobile_dock_links": mobile_dock_links,
        "mobile_command_title": command_title,
        "mobile_command_copy": command_copy,
    }
