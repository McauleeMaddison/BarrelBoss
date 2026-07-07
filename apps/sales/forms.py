from django import forms

from .models import PosIntegration, PosLocationMapping, SalesSnapshot


class SalesSnapshotForm(forms.ModelForm):
    class Meta:
        model = SalesSnapshot
        fields = [
            "business_date",
            "location_name",
            "source",
            "sync_mode",
            "external_reference",
            "gross_sales",
            "net_sales",
            "discounts",
            "refunds",
            "tips",
            "transactions",
            "covers",
            "cash_sales",
            "card_sales",
            "digital_sales",
            "beer_sales",
            "spirits_sales",
            "wine_sales",
            "soft_sales",
            "food_sales",
            "other_sales",
            "notes",
        ]
        widgets = {
            "business_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        gross_sales = cleaned_data.get("gross_sales") or 0
        net_sales = cleaned_data.get("net_sales") or 0

        if gross_sales and net_sales and net_sales > gross_sales:
            self.add_error(
                "net_sales",
                "Net sales cannot exceed gross sales for the same snapshot.",
            )

        return cleaned_data


class PosIntegrationForm(forms.ModelForm):
    class Meta:
        model = PosIntegration
        fields = [
            "label",
            "provider",
            "account_identifier",
            "api_base_url",
            "webhook_secret",
            "sync_interval_minutes",
            "is_enabled",
            "auto_sync_enabled",
            "webhook_enabled",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class PosLocationMappingForm(forms.ModelForm):
    class Meta:
        model = PosLocationMapping
        fields = [
            "integration",
            "external_location_id",
            "external_location_name",
            "internal_location_name",
            "is_primary",
            "is_active",
            "auto_import_enabled",
        ]
