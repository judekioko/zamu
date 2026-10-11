from datetime import date

from django.conf import settings
from django.db import models


def normalize_phone(raw):
    digits = ''.join(c for c in raw if c.isdigit())
    if digits.startswith('0'):
        digits = '254' + digits[1:]
    elif digits.startswith(('7', '1')) and len(digits) == 9:
        digits = '254' + digits
    return digits


class Location(models.Model):
    """A route, stage, town or yard a vehicle works from."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['owner', 'name'], name='unique_location_per_owner')]

    def __str__(self):
        return self.name


class Vehicle(models.Model):
    KINDS = [('matatu', 'Matatu'), ('boda', 'Boda boda'), ('taxi', 'Taxi'),
             ('tuktuk', 'Tuk-tuk'), ('truck', 'Truck'), ('other', 'Other')]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField('Type', max_length=8, choices=KINDS, default='matatu')
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='vehicles')
    reg = models.CharField('Registration', max_length=20)
    nickname = models.CharField(max_length=40, blank=True)
    driver_name = models.CharField(max_length=80, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    daily_target = models.PositiveIntegerField('Daily target (KES)')
    start_date = models.DateField('Tracking starts', default=date.today)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['reg']
        constraints = [models.UniqueConstraint(fields=['owner', 'reg'], name='unique_reg_per_owner')]

    def __str__(self):
        return self.label

    @property
    def label(self):
        return f'{self.reg} ({self.nickname})' if self.nickname else self.reg

    def save(self, *args, **kwargs):
        self.reg = self.reg.strip().upper()
        self.driver_phone = normalize_phone(self.driver_phone)
        super().save(*args, **kwargs)


class Remittance(models.Model):
    """Money handed to the owner for a day. An 'off' record means no target that day."""
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='remittances')
    date = models.DateField(default=date.today)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='remittances')
    amount = models.PositiveIntegerField(default=0)
    is_off = models.BooleanField(default=False)
    receipt = models.CharField('M-Pesa receipt', max_length=30, blank=True, db_index=True)
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-date', '-id']


class Expense(models.Model):
    CATEGORIES = [('fuel', 'Fuel'), ('repair', 'Repair'), ('service', 'Service'),
                  ('insurance', 'Insurance / licence'), ('fine', 'Fine'), ('other', 'Other')]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField(default=date.today)
    category = models.CharField(max_length=12, choices=CATEGORIES, default='repair')
    amount = models.PositiveIntegerField()
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-date', '-id']


class Move(models.Model):
    """A vehicle moving from one location to another."""
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='moves')
    from_location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='+')
    to_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='+')
    date = models.DateField(default=date.today)
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['-date', '-id']


class PayerAlias(models.Model):
    """Remembers that payments from this sender belong to this vehicle."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=80)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='aliases')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'key'], name='unique_alias_per_owner')]
