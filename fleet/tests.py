from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import stats
from .models import Expense, Remittance, Vehicle

TODAY = date(2026, 10, 15)  # a Thursday


def make_vehicle(user, start=date(2026, 10, 1), target=1000, reg='kca 123a'):
    return Vehicle.objects.create(owner=user, reg=reg, daily_target=target, start_date=start,
                                  driver_name='Otieno', driver_phone='0712345678')


class StatsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('amina', password='pw')
        self.v = make_vehicle(self.user)

    def test_arrears_skip_off_days_and_count_payments(self):
        # Days 1-14 owed = 14 * 1000; one off day removes 1000; 10 days paid in full.
        Remittance.objects.create(vehicle=self.v, date=date(2026, 10, 5), is_off=True)
        for n in range(1, 15):
            if n not in (5, 6, 7, 8):
                Remittance.objects.create(vehicle=self.v, date=date(2026, 10, n), amount=1000)
        snap = stats.snapshot(self.v, TODAY)
        self.assertEqual(snap.arrears, 3000)  # 13 working days owed, 10 paid

    def test_todays_payment_reduces_arrears_but_target_not_due_until_tomorrow(self):
        snap = stats.snapshot(self.v, date(2026, 10, 1))
        self.assertEqual(snap.arrears, 0)
        self.assertEqual(snap.status, 'waiting')
        Remittance.objects.create(vehicle=self.v, date=date(2026, 10, 1), amount=1000)
        snap = stats.snapshot(self.v, date(2026, 10, 1))
        self.assertEqual((snap.status, snap.arrears), ('paid', -1000))

    def test_month_net(self):
        Remittance.objects.create(vehicle=self.v, date=date(2026, 10, 2), amount=1500)
        Expense.objects.create(vehicle=self.v, date=date(2026, 10, 3), amount=400, category='fuel')
        Expense.objects.create(vehicle=self.v, date=date(2026, 9, 30), amount=999)
        snap = stats.snapshot(self.v, TODAY)
        self.assertEqual((snap.month_collected, snap.month_expenses, snap.month_net), (1500, 400, 1100))

    def test_tracking_start_limits_expected(self):
        late = Vehicle.objects.create(owner=self.user, reg='KDD 1', daily_target=500,
                                      start_date=date(2026, 10, 13))
        self.assertEqual(stats.snapshot(late, TODAY).month_expected, 500 * 3)


class ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('amina', password='pw')
        self.client.login(username='amina', password='pw')
        self.v = make_vehicle(self.user, start=date.today())

    def test_dashboard_quick_paid_and_off(self):
        self.client.post(reverse('quick_paid', args=[self.v.pk]), {'amount': '700'})
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'Short: 700')
        self.client.post(reverse('quick_paid', args=[self.v.pk]), {'amount': '300'})
        self.assertContains(self.client.get(reverse('dashboard')), 'Paid 1,000')

    def test_off_day(self):
        self.client.post(reverse('mark_off', args=[self.v.pk]))
        self.client.post(reverse('mark_off', args=[self.v.pk]))
        self.assertEqual(self.v.remittances.filter(is_off=True).count(), 1)
        self.assertContains(self.client.get(reverse('dashboard')), 'Off today')

    def test_whatsapp_message_when_behind(self):
        v = make_vehicle(self.user, start=date.today() - timedelta(days=3), reg='KBB 9')
        page = self.client.get(reverse('vehicle', args=[v.pk]))
        self.assertContains(page, 'wa.me/254712345678')
        self.assertContains(page, 'KES 3,000 behind')

    def test_other_owners_cannot_see_vehicle(self):
        User.objects.create_user('bob', password='pw')
        self.client.login(username='bob', password='pw')
        self.assertEqual(self.client.get(reverse('vehicle', args=[self.v.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('quick_paid', args=[self.v.pk]), {'amount': '5'}).status_code, 404)

    def test_report_and_duplicate_reg(self):
        self.assertEqual(self.client.get(reverse('report')).status_code, 200)
        r = self.client.post(reverse('vehicle_add'), {'reg': 'KCA 123A', 'daily_target': 800,
                                                      'start_date': date.today().isoformat(), 'active': 'on'})
        self.assertContains(r, 'already have this vehicle')
