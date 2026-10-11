import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from fleet.models import Expense, Remittance, Vehicle

DEMO_USER, DEMO_PASSWORD = 'demo', 'demo-pass-123'  # local dev only


class Command(BaseCommand):
    help = 'Create a demo owner with three vehicles and 30 days of history (local use only).'

    def handle(self, *args, **opts):
        user, created = User.objects.get_or_create(username=DEMO_USER)
        if not created:
            self.stdout.write('Demo user already exists; nothing changed.')
            return
        user.set_password(DEMO_PASSWORD)
        user.save()
        rng = random.Random(7)
        today = date.today()
        fleet = [('KDA 214K', 'Matatu 1', 'Otieno', '0712000111', 3000, 0.9),
                 ('KCX 880M', 'Matatu 2', 'Wafula', '0722000222', 2500, 0.6),
                 ('KMFB 042T', 'Boda Blue', 'Kevin', '0733000333', 700, 0.8)]
        for reg, nick, driver, phone, target, reliability in fleet:
            v = Vehicle.objects.create(owner=user, reg=reg, nickname=nick, driver_name=driver,
                                       driver_phone=phone, daily_target=target,
                                       start_date=today - timedelta(days=30))
            for n in range(30, 0, -1):
                day = today - timedelta(days=n)
                if day.weekday() == 6 and rng.random() < 0.6:
                    Remittance.objects.create(vehicle=v, date=day, is_off=True, note='Off day')
                elif rng.random() < reliability:
                    Remittance.objects.create(vehicle=v, date=day, amount=target)
                elif rng.random() < 0.5:
                    Remittance.objects.create(vehicle=v, date=day, amount=target // 2, note='Half')
            Expense.objects.create(vehicle=v, date=today - timedelta(days=9), category='service',
                                   amount=target * 2, note='Oil and filters')
            Expense.objects.create(vehicle=v, date=today - timedelta(days=3), category='repair',
                                   amount=target, note='Brake pads')
        self.stdout.write(f'Created demo owner "{DEMO_USER}" (password in seed_demo.py).')
