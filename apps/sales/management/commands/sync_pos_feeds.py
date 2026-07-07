from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.sales.models import PosIntegration, PosSyncRun
from apps.sales.services import parse_business_date, sync_integration


class Command(BaseCommand):
    help = "Run scheduled POS sync imports for enabled connectors."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            choices=PosIntegration.Provider.values,
            help="Limit the run to a single provider.",
        )
        parser.add_argument(
            "--integration",
            type=int,
            help="Limit the run to a specific integration id.",
        )
        parser.add_argument(
            "--business-date",
            help="Override the business date in YYYY-MM-DD format.",
        )

    def handle(self, *args, **options):
        business_date = parse_business_date(options.get("business_date"))
        integrations = PosIntegration.objects.filter(is_enabled=True)

        if options.get("provider"):
            integrations = integrations.filter(provider=options["provider"])
        if options.get("integration"):
            integrations = integrations.filter(pk=options["integration"])

        integrations = list(integrations.order_by("label"))
        if not integrations:
            self.stdout.write("No enabled connectors matched the requested filters.")
            return

        completed = 0
        failures = []
        for integration in integrations:
            try:
                run = sync_integration(
                    integration,
                    business_date=business_date,
                    trigger_type=PosSyncRun.TriggerType.SCHEDULED,
                )
                completed += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{integration.label}: imported {run.snapshots_imported} snapshot(s) "
                        f"for {business_date:%Y-%m-%d}."
                    )
                )
            except Exception as exc:
                failures.append((integration.label, str(exc)))
                self.stdout.write(
                    self.style.ERROR(f"{integration.label}: sync failed - {exc}")
                )

        self.stdout.write(
            f"Completed {completed} sync run(s) at {timezone.localtime():%Y-%m-%d %H:%M}."
        )
        if failures:
            failure_labels = ", ".join(label for label, _message in failures)
            self.stdout.write(self.style.WARNING(f"Failures: {failure_labels}"))
