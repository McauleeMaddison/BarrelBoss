from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Order, OrderItem


class OrderForm(forms.ModelForm):
    def __init__(self, *args, is_management=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_management = is_management
        if not is_management:
            self.fields.pop("status", None)

    class Meta:
        model = Order
        fields = ["supplier", "order_date", "delivery_date", "status", "notes"]
        widgets = {
            "order_date": forms.DateInput(attrs={"type": "date"}),
            "delivery_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ["stock_item", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock_item"].queryset = self.fields["stock_item"].queryset.filter(
            is_active=True
        )


class BaseOrderItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        has_item = False
        for form in self.forms:
            if form.cleaned_data.get("DELETE"):
                continue
            stock_item = form.cleaned_data.get("stock_item")
            quantity = form.cleaned_data.get("quantity")
            if stock_item and quantity:
                has_item = True

        if not has_item:
            raise forms.ValidationError("Add at least one order item.")


OrderItemFormSet = inlineformset_factory(
    Order,
    OrderItem,
    form=OrderItemForm,
    formset=BaseOrderItemFormSet,
    extra=2,
    can_delete=True,
)
