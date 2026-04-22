from django.db import models


class Supplier(models.Model):
    class CategorySupplied(models.TextChoices):
        BEER_BARRELS = "BEER_BARRELS", "Beer Barrels"
        SPIRITS = "SPIRITS", "Spirits"
        WINE = "WINE", "Wine"
        SOFT_DRINKS = "SOFT_DRINKS", "Soft Drinks"
        MIXERS = "MIXERS", "Mixers"
        GLASSWARE = "GLASSWARE", "Glassware"
        CLEANING = "CLEANING", "Cleaning Supplies"
        OTHER = "OTHER", "Other"

    name = models.CharField(max_length=150, unique=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    category_supplied = models.CharField(
        max_length=40,
        choices=CategorySupplied.choices,
        default=CategorySupplied.OTHER,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
