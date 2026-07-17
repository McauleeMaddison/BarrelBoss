def build_module_link(label, url):
    return {"label": label, "url": url}


def build_module_panel(
    *,
    hero_class,
    kicker,
    badge,
    title,
    copy,
    primary_title,
    primary_copy,
    primary_url,
    primary_label,
    utility_links=None,
    toolbar_notes=None,
):
    return {
        "hero_class": hero_class,
        "kicker": kicker,
        "badge": badge,
        "title": title,
        "copy": copy,
        "primary_kicker": "Next step",
        "primary_title": primary_title,
        "primary_copy": primary_copy,
        "primary_url": primary_url,
        "primary_label": primary_label,
        "utility_links": utility_links or [],
        "toolbar_notes": toolbar_notes or [],
    }


def build_module_snapshot(
    *,
    label,
    state,
    tone,
    value,
    copy,
    action_label=None,
    action_url=None,
):
    snapshot = {
        "label": label,
        "state": state,
        "tone": tone,
        "value": value,
        "copy": copy,
    }
    if action_label and action_url:
        snapshot["action_label"] = action_label
        snapshot["action_url"] = action_url
    return snapshot
