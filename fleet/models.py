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


class Vehicle(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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
    amount = models.PositiveIntegerField(default=0)
    is_off = models.BooleanField(default=False)
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
