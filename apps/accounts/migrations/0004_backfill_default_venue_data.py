from django.db import migrations


def backfill_default_venue_data(apps, schema_editor):
    Organisation = apps.get_model("accounts", "Organisation")
    Venue = apps.get_model("accounts", "Venue")
    StaffProfile = apps.get_model("accounts", "StaffProfile")
    VenueMembership = apps.get_model("accounts", "VenueMembership")
    User = apps.get_model("auth", "User")
    Supplier = apps.get_model("suppliers", "Supplier")
    StockItem = apps.get_model("stock", "StockItem")
    Order = apps.get_model("orders", "Order")
    Checklist = apps.get_model("checklists", "Checklist")
    Breakage = apps.get_model("breakages", "Breakage")
    Shift = apps.get_model("shifts", "Shift")
    AuditEvent = apps.get_model("audit", "AuditEvent")
    SalesSnapshot = apps.get_model("sales", "SalesSnapshot")
    PosIntegration = apps.get_model("sales", "PosIntegration")

    organisation = Organisation.objects.order_by("id").first()
    if organisation is None:
        organisation = Organisation.objects.create(
            name="BarrelBoss",
            slug="barrelboss",
            is_active=True,
        )

    venue = Venue.objects.order_by("id").first()
    if venue is None:
        venue = Venue.objects.create(
            organisation=organisation,
            name="Main Venue",
            slug="main-venue",
            timezone="Europe/London",
            is_active=True,
            low_stock_buffer_percent=50,
            dashboard_focus="OPERATIONS",
            opening_handover_prompt="Opening checks complete and cellar/service prep confirmed.",
            closing_handover_prompt="Closing checks complete and handover notes recorded.",
        )

    for user in User.objects.order_by("id"):
        profile = StaffProfile.objects.filter(user_id=user.id).first()
        VenueMembership.objects.get_or_create(
            venue_id=venue.id,
            user_id=user.id,
            defaults={
                "role": (
                    profile.role
                    if profile is not None
                    else ("LANDLORD" if user.is_superuser else "STAFF")
                ),
                "is_active": profile.is_active if profile is not None else True,
                "is_default": True,
                "notify_on_shift_assignment": (
                    profile.notify_on_shift_assignment if profile is not None else True
                ),
                "job_title": profile.job_title if profile is not None else "",
            },
        )

    Supplier.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    StockItem.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    Order.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    Checklist.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    Breakage.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    Shift.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    AuditEvent.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    SalesSnapshot.objects.filter(venue__isnull=True).update(venue_id=venue.id)
    PosIntegration.objects.filter(venue__isnull=True).update(venue_id=venue.id)


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_organisation_venue_venueinvite_venuemembership_and_more"),
        ("audit", "0002_auditevent_venue_and_more"),
        ("breakages", "0002_breakage_resolution_notes_breakage_resolved_at_and_more"),
        ("checklists", "0002_checklisttemplate_dailysignoff_checklist_venue_and_more"),
        ("orders", "0002_order_received_at_order_received_by_order_venue_and_more"),
        ("sales", "0003_remove_salessnapshot_uniq_sales_snapshot_location_source_date_and_more"),
        ("shifts", "0002_shift_handover_completed_at_and_more"),
        ("stock", "0002_stockitem_last_counted_at_stockitem_venue_and_more"),
        ("suppliers", "0002_supplier_venue_alter_supplier_name_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_default_venue_data, noop),
    ]
