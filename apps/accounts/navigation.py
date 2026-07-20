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


def _build_url(url_name, *, query=None, fragment=None):
    default_fragments = {
        "checklists:list": "checklists-section-board",
        "stock:list": "stock-section-board",
        "shifts:list": "shifts-section-board",
        "orders:list": "orders-section-board",
        "breakages:list": "breakages-section-board",
        "sales:list": "salesTable",
    }
    url = reverse(url_name)
    if query:
        url = f"{url}?{query}"
    target_fragment = fragment or default_fragments.get(url_name)
    if target_fragment:
        url = f"{url}#{target_fragment}"
    return url


def _nav_item(
    current,
    *,
    label,
    url_name,
    group,
    query=None,
    fragment=None,
    description="",
):
    return {
        "label": label,
        "url": _build_url(url_name, query=query, fragment=fragment),
        "active": _group_active(current, group),
        "description": description,
    }


def _action_item(*, label, url_name, copy, query=None, fragment=None, emphasis="default"):
    return {
        "label": label,
        "url": _build_url(url_name, query=query, fragment=fragment),
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
                description="Overview",
            ),
            _nav_item(
                current,
                label="Tasks",
                url_name="checklists:list",
                group="checklists",
                description="Standards",
            ),
            _nav_item(
                current,
                label="Stock",
                url_name="stock:list",
                group="stock",
                description="Inventory",
            ),
            _nav_item(
                current,
                label="Orders",
                url_name="orders:list",
                group="orders",
                description="Purchasing",
            ),
            _nav_item(
                current,
                label="Rota",
                url_name="shifts:list",
                group="shifts",
                description="Scheduling",
            ),
        ]
        secondary_links = [
            _nav_item(
                current,
                label="Breakages",
                url_name="breakages:list",
                group="breakages",
                description="Incidents",
            ),
            _nav_item(
                current,
                label="Sales",
                url_name="sales:list",
                group="sales",
                description="Revenue",
            ),
            _nav_item(
                current,
                label="Suppliers",
                url_name="suppliers:list",
                group="suppliers",
                description="Vendors",
            ),
            _nav_item(
                current,
                label="Staff",
                url_name="staff",
                group="staff",
                description="Team",
            ),
            _nav_item(
                current,
                label="Reports",
                url_name="reports",
                group="reports",
                description="Exports",
            ),
            _nav_item(
                current,
                label="Activity",
                url_name="audit:list",
                group="audit",
                description="Audit",
            ),
            _nav_item(
                current,
                label="Settings",
                url_name="settings",
                group="settings",
                description="Alerts",
            ),
        ]
        quick_actions = []
        bar_title = "Management workspace"
        bar_copy = "Keep the core management boards close."
        secondary_title = "Support"
        command_title = "More tools"
        command_copy = "Open the remaining management tools."
        mobile_dock_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Overview",
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
                description="Cellar",
            ),
            _nav_item(
                current,
                label="Deliveries",
                url_name="orders:list",
                group="orders",
                query="preset=pending",
                description="Inbound",
            ),
        ]
        mobile_command_links = [
            _nav_item(
                current,
                label="Rota",
                url_name="shifts:list",
                group="shifts",
                description="Scheduling",
            ),
            _nav_item(
                current,
                label="Breakages",
                url_name="breakages:list",
                group="breakages",
                description="Incidents",
            ),
            _nav_item(
                current,
                label="Sales",
                url_name="sales:list",
                group="sales",
                description="Revenue",
            ),
            _nav_item(
                current,
                label="Suppliers",
                url_name="suppliers:list",
                group="suppliers",
                description="Vendors",
            ),
            _nav_item(
                current,
                label="Staff",
                url_name="staff",
                group="staff",
                description="Team",
            ),
            _nav_item(
                current,
                label="Reports",
                url_name="reports",
                group="reports",
                description="Exports",
            ),
            _nav_item(
                current,
                label="Activity",
                url_name="audit:list",
                group="audit",
                description="Audit",
            ),
            _nav_item(
                current,
                label="Settings",
                url_name="settings",
                group="settings",
                description="Alerts",
            ),
        ]
    else:
        primary_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Overview",
            ),
            _nav_item(
                current,
                label="Tasks",
                url_name="checklists:list",
                group="checklists",
                description="My queue",
            ),
            _nav_item(
                current,
                label="Stock",
                url_name="stock:list",
                group="stock",
                description="Availability",
            ),
            _nav_item(
                current,
                label="Rota",
                url_name="shifts:list",
                group="shifts",
                description="My shifts",
            ),
            _nav_item(
                current,
                label="Requests",
                url_name="orders:list",
                group="orders",
                description="My requests",
            ),
        ]
        secondary_links = [
            _nav_item(
                current,
                label="Log breakage",
                url_name="breakages:add",
                group="breakages",
                description="Record damage",
            ),
            _nav_item(
                current,
                label="Stock request",
                url_name="orders:add",
                group="orders",
                description="Raise request",
            ),
        ]
        quick_actions = []
        bar_title = "Shift workspace"
        bar_copy = "Keep the core shift tools close."
        secondary_title = "Report & request"
        command_title = "More tools"
        command_copy = "Open the remaining shift tools."
        mobile_dock_links = [
            _nav_item(
                current,
                label="Today",
                url_name=home_url_name,
                group="home",
                description="Overview",
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
                label="Stock",
                url_name="stock:list",
                group="stock",
                description="Availability",
            ),
            _nav_item(
                current,
                label="Rota",
                url_name="shifts:list",
                group="shifts",
                description="My shifts",
            ),
        ]
        mobile_command_links = [
            _nav_item(
                current,
                label="Requests",
                url_name="orders:list",
                group="orders",
                description="My requests",
            ),
            _nav_item(
                current,
                label="Request stock",
                url_name="orders:add",
                group="orders",
                description="Raise request",
            ),
            _nav_item(
                current,
                label="Report breakage",
                url_name="breakages:add",
                group="breakages",
                description="Log issue",
            ),
        ]

    active_label = next(
        (link["label"] for link in [*primary_links, *secondary_links] if link["active"]),
        "Workspace",
    )

    return {
        "workspace_primary_links": primary_links,
        "workspace_secondary_links": secondary_links,
        "workspace_secondary_title": secondary_title,
        "workspace_quick_actions": quick_actions,
        "workspace_bar_title": bar_title,
        "workspace_bar_copy": bar_copy,
        "workspace_active_label": active_label,
        "mobile_dock_links": mobile_dock_links,
        "mobile_command_links": mobile_command_links,
        "mobile_command_title": command_title,
        "mobile_command_copy": command_copy,
        "mobile_command_button_label": "More",
        "mobile_command_button_copy": "More tools",
    }
