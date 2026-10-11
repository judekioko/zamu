from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import stats
from .models import Expense, Location, PayerAlias, Remittance, Vehicle

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


class LocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('amina', password='pw')
        self.client.login(username='amina', password='pw')

    def test_add_with_location_then_move_and_earnings_follow(self):
        self.client.post(reverse('vehicle_add'), {
            'reg': 'kca 1a', 'kind': 'matatu', 'location_name': 'Githurai route', 'daily_target': 2000,
            'start_date': date.today().isoformat(), 'active': 'on'})
        v = Vehicle.objects.get()
        first = v.location
        self.assertEqual(first.name, 'Githurai route')
        self.client.post(reverse('quick_paid', args=[v.pk]), {'amount': '2000'})
        self.client.post(reverse('move', args=[v.pk]), {
            'to_name': 'githurai ROUTE', 'date': date.today().isoformat()})  # same place: ignored
        self.assertEqual(v.moves.count(), 1)
        self.client.post(reverse('move', args=[v.pk]), {
            'to_name': 'Thika Road', 'date': date.today().isoformat(), 'note': 'Slow on Githurai'})
        v.refresh_from_db()
        self.assertEqual(v.location.name, 'Thika Road')
        self.assertEqual(v.moves.count(), 2)
        self.client.post(reverse('quick_paid', args=[v.pk]), {'amount': '500'})
        page = self.client.get(reverse('report'))
        self.assertContains(page, 'Githurai route')
        self.assertContains(page, 'Thika Road')
        self.assertContains(self.client.get(reverse('dashboard') + f'?loc={v.location_id}'), 'KCA 1A')
        self.assertNotContains(self.client.get(reverse('dashboard') + f'?loc={first.pk}'), 'KCA 1A')

    def test_edit_vehicle_location_logs_move(self):
        v = Vehicle.objects.create(owner=self.user, reg='KBB 2', daily_target=700, start_date=date.today())
        self.client.post(reverse('vehicle_edit', args=[v.pk]), {
            'reg': 'KBB 2', 'kind': 'boda', 'location_name': 'Kawangware', 'daily_target': 700,
            'start_date': date.today().isoformat(), 'active': 'on'})
        v.refresh_from_db()
        self.assertEqual((v.kind, v.location.name, v.moves.count()), ('boda', 'Kawangware', 1))


SAMPLE = open('samples/mpesa_statement_sample.csv', encoding='utf-8').read()


class StatementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('amina', password='pw')
        self.client.login(username='amina', password='pw')
        self.a = Vehicle.objects.create(owner=self.user, reg='KDA 1', daily_target=3000,
                                        driver_name='Otieno', driver_phone='0712345678',
                                        start_date=date(2026, 10, 1))
        self.b = Vehicle.objects.create(owner=self.user, reg='KCX 2', daily_target=2500,
                                        driver_name='Wafula', driver_phone='0722000022',
                                        start_date=date(2026, 10, 1))
        self.c = Vehicle.objects.create(owner=self.user, reg='KMF 3', daily_target=700,
                                        driver_name='Kevin', driver_phone='0733000333',
                                        start_date=date(2026, 10, 1))

    def test_parse_skips_junk_failed_and_money_out(self):
        from . import mpesa
        rows = mpesa.parse(SAMPLE)
        self.assertEqual([r['receipt'] for r in rows],
                         ['TJB1A2B3C4', 'TJB1A2B3C5', 'TJB1A2B3C6', 'TJB1A2B3C7'])
        self.assertEqual(rows[1]['amount'], 2500)
        self.assertEqual(rows[0]['date'], date(2026, 10, 9))

    def test_suggest_by_full_phone_masked_phone_and_unknown(self):
        from . import mpesa
        rows = mpesa.parse(SAMPLE)
        vs = [self.a, self.b, self.c]
        got = [mpesa.suggest(r, vs, {}) for r in rows]
        self.assertEqual(got, [self.a.pk, self.b.pk, self.c.pk, None])

    def test_bad_file(self):
        from . import mpesa
        with self.assertRaises(mpesa.StatementError):
            mpesa.parse('hello,world\n1,2\n')

    def test_upload_confirm_dedupe_and_remember(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        up = SimpleUploadedFile('s.csv', SAMPLE.encode(), content_type='text/csv')
        page = self.client.post(reverse('import'), {'statement': up})
        self.assertContains(page, '3</strong> matched')
        post = {'action': 'confirm', 'vehicle_0': self.a.pk, 'vehicle_1': self.b.pk,
                'vehicle_2': self.c.pk, 'vehicle_3': self.a.pk, 'remember_3': 'on'}
        self.client.post(reverse('import'), post)
        self.assertEqual(Remittance.objects.count(), 4)
        self.assertEqual(Remittance.objects.get(receipt='TJB1A2B3C5').vehicle, self.b)
        self.assertEqual(Remittance.objects.get(receipt='TJB1A2B3C4').date, date(2026, 10, 9))
        self.assertEqual(PayerAlias.objects.get().vehicle, self.a)
        # Second upload: everything is already imported, the stranger is now remembered
        up = SimpleUploadedFile('s.csv', SAMPLE.encode(), content_type='text/csv')
        page = self.client.post(reverse('import'), {'statement': up})
        self.assertContains(page, '4</strong> already imported')
        self.client.post(reverse('import'), {'action': 'confirm', 'vehicle_0': self.a.pk})
        self.assertEqual(Remittance.objects.count(), 4)  # duplicate receipt refused

    def test_other_owners_vehicle_cannot_be_used(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bob = User.objects.create_user('bob', password='pw')
        theirs = Vehicle.objects.create(owner=bob, reg='BOB 1', daily_target=1)
        up = SimpleUploadedFile('s.csv', SAMPLE.encode(), content_type='text/csv')
        self.client.post(reverse('import'), {'statement': up})
        self.client.post(reverse('import'), {'action': 'confirm', 'vehicle_0': theirs.pk})
        self.assertEqual(Remittance.objects.count(), 0)
