from django.core.validators import MinValueValidator
from django.db import models


class StockItem(models.Model):
    class Category(models.TextChoices):
        BEER_BARRELS = "BEER_BARRELS", "Beer Barrels"
        SPIRITS = "SPIRITS", "Spirits"
        WINE = "WINE", "Wine"
        SOFT_DRINKS = "SOFT_DRINKS", "Soft Drinks"
        MIXERS = "MIXERS", "Mixers"
        GLASSWARE = "GLASSWARE", "Glassware"
        CLEANING = "CLEANING", "Cleaning Supplies"
        GARNISHES = "GARNISHES", "Garnishes"
        SNACKS = "SNACKS", "Snacks"

    class Unit(models.TextChoices):
        BARRELS = "BARRELS", "Barrels"
        BOTTLES = "BOTTLES", "Bottles"
        CANS = "CANS", "Cans"
        BOXES = "BOXES", "Boxes"
        LITRES = "LITRES", "Litres"
        KG = "KG", "Kg"
        UNITS = "UNITS", "Units"

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=40, choices=Category.choices)
    quantity = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.UNITS)
    minimum_level = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_items",
    )
    notes = models.TextField(blank=True)
    last_restocked = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.minimum_level
