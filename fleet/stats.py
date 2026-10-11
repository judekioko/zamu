"""All money maths for a vehicle. Amounts are whole KES."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta


def _days(start, end):
    return (end - start).days + 1 if end >= start else 0


@dataclass
class Snapshot:
    vehicle: object
    today: date
    paid_today: int
    off_today: bool
    arrears: int            # expected through yesterday minus everything collected so far
    month_collected: int
    month_expected: int
    month_expenses: int

    @property
    def status(self):
        if self.off_today:
            return 'off'
        if self.paid_today >= self.vehicle.daily_target:
            return 'paid'
        return 'short' if self.paid_today else 'waiting'

    @property
    def month_net(self):
        return self.month_collected - self.month_expenses

    @property
    def month_shortfall(self):
        return max(self.month_expected - self.month_collected, 0)


def expected(vehicle, rows, start, end):
    """Target owed for days in [start, end], skipping days marked off."""
    start = max(start, vehicle.start_date)
    off = {r.date for r in rows if r.is_off}
    return vehicle.daily_target * sum(
        1 for n in range(_days(start, end)) if (start + timedelta(days=n)) not in off)


def collected(rows, start, end):
    return sum(r.amount for r in rows if start <= r.date <= end)


def month_bounds(day):
    first = day.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


def snapshot(vehicle, today=None, month=None):
    """`month` is any date inside the month to summarise (default: today's month)."""
    today = today or date.today()
    rows = list(vehicle.remittances.all())
    expenses = list(vehicle.expenses.all())
    first, last = month_bounds(month or today)
    cutoff = min(last, today)
    return Snapshot(
        vehicle=vehicle, today=today,
        paid_today=collected(rows, today, today),
        off_today=any(r.is_off and r.date == today for r in rows),
        arrears=expected(vehicle, rows, vehicle.start_date, today - timedelta(days=1))
        - collected(rows, date.min, today),
        month_collected=collected(rows, first, last),
        month_expected=expected(vehicle, rows, first, cutoff),
        month_expenses=sum(e.amount for e in expenses if first <= e.date <= last),
    )


def daily_table(vehicle, days=30, today=None):
    """Last `days` days, newest first: (date, paid, target, off, diff)."""
    today = today or date.today()
    by_day = defaultdict(int)
    off = set()
    for r in vehicle.remittances.all():
        by_day[r.date] += r.amount
        if r.is_off:
            off.add(r.date)
    out = []
    for n in range(days):
        d = today - timedelta(days=n)
        if d < vehicle.start_date:
            break
        target = 0 if d in off else vehicle.daily_target
        out.append((d, by_day[d], target, d in off, by_day[d] - target))
    return out
