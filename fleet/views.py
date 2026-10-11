from datetime import date, timedelta
from urllib.parse import quote

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import stats
from .forms import ExpenseForm, RemittanceForm, SignupForm, VehicleForm
from .models import Expense, Remittance, Vehicle


def _vehicle(request, pk):
    return get_object_or_404(Vehicle, pk=pk, owner=request.user)


def _fleet(user):
    return Vehicle.objects.filter(owner=user, active=True).prefetch_related('remittances', 'expenses')


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.save())
        return redirect('vehicle_add')
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def dashboard(request):
    snaps = [stats.snapshot(v) for v in _fleet(request.user)]
    order = {'waiting': 0, 'short': 1, 'paid': 2, 'off': 3}
    snaps.sort(key=lambda s: (order[s.status], -s.arrears))
    return render(request, 'dashboard.html', {
        'snaps': snaps,
        'today': date.today(),
        'collected_today': sum(s.paid_today for s in snaps),
        'target_today': sum(s.vehicle.daily_target for s in snaps if not s.off_today),
        'arrears_total': sum(max(s.arrears, 0) for s in snaps),
        'month_net': sum(s.month_net for s in snaps),
    })


@login_required
def vehicle_form(request, pk=None):
    instance = _vehicle(request, pk) if pk else None
    form = VehicleForm(request.POST or None, instance=instance, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        v = form.save(commit=False)
        v.owner = request.user
        v.save()
        return redirect('vehicle', pk=v.pk)
    return render(request, 'vehicle_form.html', {'form': form, 'editing': instance})


@login_required
def vehicle_detail(request, pk):
    v = _vehicle(request, pk)
    rform = RemittanceForm(request.POST or None, initial={'amount': v.daily_target})
    if request.method == 'POST' and rform.is_valid():
        r = rform.save(commit=False)
        r.vehicle = v
        r.save()
        return redirect('vehicle', pk=v.pk)
    snap = stats.snapshot(v)
    text = ''
    if snap.arrears > 0:
        who = v.driver_name or 'driver'
        text = (f'Hello {who}, {v.reg} is KES {snap.arrears:,} behind on remittance as at '
                f'{date.today():%d %b}. Please send today\'s KES {v.daily_target:,} and part of the '
                f'balance. Let me know when you will clear the rest.')
    return render(request, 'vehicle.html', {
        'v': v, 'snap': snap, 'rform': rform, 'eform': ExpenseForm(),
        'table': stats.daily_table(v), 'expenses': v.expenses.all()[:15],
        'text': text, 'wa': f'https://wa.me/{v.driver_phone}?text={quote(text)}'
        if text and v.driver_phone else '',
    })


@login_required
@require_POST
def quick_paid(request, pk):
    v = _vehicle(request, pk)
    try:
        amount = int(request.POST.get('amount', ''))
    except ValueError:
        amount = 0
    if amount > 0:
        Remittance.objects.create(vehicle=v, amount=amount)
    return redirect('dashboard')


@login_required
@require_POST
def mark_off(request, pk):
    v = _vehicle(request, pk)
    Remittance.objects.get_or_create(vehicle=v, date=date.today(), is_off=True,
                                     defaults={'amount': 0, 'note': 'Off day'})
    return redirect('dashboard')


@login_required
@require_POST
def add_expense(request, pk):
    v = _vehicle(request, pk)
    form = ExpenseForm(request.POST)
    if form.is_valid():
        e = form.save(commit=False)
        e.vehicle = v
        e.save()
    return redirect('vehicle', pk=v.pk)


@login_required
@require_POST
def delete_remittance(request, pk):
    r = get_object_or_404(Remittance, pk=pk, vehicle__owner=request.user)
    vid = r.vehicle_id
    r.delete()
    return redirect('vehicle', pk=vid)


@login_required
@require_POST
def delete_expense(request, pk):
    e = get_object_or_404(Expense, pk=pk, vehicle__owner=request.user)
    vid = e.vehicle_id
    e.delete()
    return redirect('vehicle', pk=vid)


@login_required
def report(request):
    today = date.today()
    try:
        y, m = map(int, request.GET.get('month', '').split('-'))
        day = date(y, m, 1)
    except ValueError:
        day = today.replace(day=1)
    if day > today:
        raise Http404
    snaps = sorted((stats.snapshot(v, today, day) for v in _fleet(request.user)),
                   key=lambda s: -s.month_net)
    prev = (day - timedelta(days=1)).replace(day=1)
    nxt = (day + timedelta(days=32)).replace(day=1)
    return render(request, 'report.html', {
        'snaps': snaps, 'day': day, 'prev': prev, 'next': nxt if nxt <= today else None,
        'collected': sum(s.month_collected for s in snaps),
        'expected': sum(s.month_expected for s in snaps),
        'expenses': sum(s.month_expenses for s in snaps),
        'net': sum(s.month_net for s in snaps),
    })
