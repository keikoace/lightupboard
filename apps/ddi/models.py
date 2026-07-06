"""
DDI (Direct Dial-In / inbound number) management.
"""
from django.db import models
from apps.core.models import Company, Destination


class DDIProfile(models.Model):
    """Routing/billing profile for a group of DDI numbers."""
    name = models.CharField(max_length=200)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='ddi_profiles')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class DDINumber(models.Model):
    """An individual DDI/DID number."""
    number = models.CharField(max_length=30, unique=True)
    country = models.CharField(max_length=100, default='Switzerland', db_index=True)
    vendor = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ddi_numbers_as_vendor',
        help_text='Provider/carrier who supplies this number to Lightup.',
    )
    customer = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name='ddi_numbers')
    destination = models.ForeignKey(Destination, null=True, blank=True, on_delete=models.SET_NULL)
    buy_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    sell_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    is_active = models.BooleanField(default=True)
    ported_in = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return self.number


class DDIRoute(models.Model):
    """Routing rule: which supplier/switch handles a DDI profile."""
    profile = models.ForeignKey(DDIProfile, on_delete=models.CASCADE, related_name='routes')
    supplier = models.ForeignKey(Company, on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField(default=1)
    weight = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['priority']

    def __str__(self):
        return f'{self.profile} → {self.supplier} (pri {self.priority})'
