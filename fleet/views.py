from datetime import date, timedelta
from urllib.parse import quote

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import mpesa, stats
from .forms import ExpenseForm, MoveForm, RemittanceForm, SignupForm, VehicleForm
from .models import Expense, Location, Move, PayerAlias, Remittance, Vehicle


def _vehicle(request, pk):
    return get_object_or_404(Vehicle, pk=pk, owner=request.user)


def _fleet(user):
    return Vehicle.objects.filter(owner=user, active=True).prefetch_related('remittances', 'expenses')


def _location(user, name):
    name = ' '.join(name.split())
    if not name:
        return None
    found = Location.objects.filter(owner=user, name__iexact=name).first()
    return found or Location.objects.create(owner=user, name=name)


def _remit(vehicle, **kw):
    kw.setdefault('location', vehicle.location)
    return Remittance.objects.create(vehicle=vehicle, **kw)


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.save())
        return redirect('vehicle_add')
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def dashboard(request):
    fleet = _fleet(request.user)
    loc = request.GET.get('loc', '')
    if loc.isdigit():
        fleet = fleet.filter(location_id=int(loc))
    snaps = [stats.snapshot(v) for v in fleet]
    order = {'waiting': 0, 'short': 1, 'paid': 2, 'off': 3}
    snaps.sort(key=lambda s: (order[s.status], -s.arrears))
    return render(request, 'dashboard.html', {
        'snaps': snaps,
        'locations': Location.objects.filter(owner=request.user, vehicles__active=True).distinct(),
        'loc': loc,
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
        new_loc = _location(request.user, form.cleaned_data['location_name'])
        old_loc = instance.location if instance else None
        if new_loc != old_loc and new_loc:
            v.location = new_loc
        v.save()
        if new_loc and new_loc != old_loc:
            Move.objects.create(vehicle=v, from_location=old_loc, to_location=new_loc,
                                date=v.start_date if instance is None else date.today(),
                                note='Started here' if instance is None else '')
        return redirect('vehicle', pk=v.pk)
    return render(request, 'vehicle_form.html', {'form': form, 'editing': instance})


@login_required
def vehicle_detail(request, pk):
    v = _vehicle(request, pk)
    rform = RemittanceForm(request.POST or None, initial={'amount': v.daily_target})
    if request.method == 'POST' and rform.is_valid():
        r = rform.save(commit=False)
        r.vehicle = v
        r.location = v.location
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
        'mform': MoveForm(), 'moves': v.moves.select_related('from_location', 'to_location')[:10],
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
        _remit(v, amount=amount)
    return redirect('dashboard')


@login_required
@require_POST
def mark_off(request, pk):
    v = _vehicle(request, pk)
    if not v.remittances.filter(date=date.today(), is_off=True).exists():
        _remit(v, is_off=True, amount=0, note='Off day')
    return redirect('dashboard')


@login_required
@require_POST
def move_vehicle(request, pk):
    v = _vehicle(request, pk)
    form = MoveForm(request.POST)
    if form.is_valid():
        dest = _location(request.user, form.cleaned_data['to_name'])
        if dest and dest != v.location:
            Move.objects.create(vehicle=v, from_location=v.location, to_location=dest,
                                date=form.cleaned_data['date'], note=form.cleaned_data['note'])
            v.location = dest
            v.save()
    return redirect('vehicle', pk=v.pk)


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
    first, last = stats.month_bounds(day)
    by_loc = {}
    for r in Remittance.objects.filter(vehicle__owner=request.user, date__range=(first, last),
                                       is_off=False).select_related('location'):
        name = r.location.name if r.location else 'No location'
        by_loc[name] = by_loc.get(name, 0) + r.amount
    by_loc = sorted(by_loc.items(), key=lambda kv: -kv[1])
    prev = (day - timedelta(days=1)).replace(day=1)
    nxt = (day + timedelta(days=32)).replace(day=1)
    return render(request, 'report.html', {
        'snaps': snaps, 'by_loc': by_loc, 'day': day, 'prev': prev, 'next': nxt if nxt <= today else None,
        'collected': sum(s.month_collected for s in snaps),
        'expected': sum(s.month_expected for s in snaps),
        'expenses': sum(s.month_expenses for s in snaps),
        'net': sum(s.month_net for s in snaps),
    })


@login_required
def statement_import(request):
    """Step 1: upload a statement. Step 2 (POST with action=confirm): save the ticked rows."""
    fleet = list(Vehicle.objects.filter(owner=request.user, active=True))
    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        rows = request.session.pop('statement_rows', [])
        valid = {str(v.pk): v for v in fleet}
        saved = 0
        for i, row in enumerate(rows):
            v = valid.get(request.POST.get(f'vehicle_{i}', ''))
            if v is None:
                continue
            if row['receipt'] and Remittance.objects.filter(
                    vehicle__owner=request.user, receipt=row['receipt']).exists():
                continue
            Remittance.objects.create(
                vehicle=v, date=date.fromisoformat(row['date']), amount=row['amount'],
                location=v.location, receipt=row['receipt'],
                note=f"M-Pesa {row['details'][:80]}".strip())
            if request.POST.get(f'remember_{i}'):
                PayerAlias.objects.update_or_create(owner=request.user, key=row['key'],
                                                    defaults={'vehicle': v})
            saved += 1
        messages.success(request, f'Imported {saved} payment(s).')
        return redirect('dashboard')

    error = ''
    if request.method == 'POST' and request.FILES.get('statement'):
        f = request.FILES['statement']
        if f.size > 5_000_000:
            error = 'That file is too big (5 MB limit).'
        else:
            try:
                parsed = mpesa.parse(f.read())
            except mpesa.StatementError as e:
                error = str(e)
            else:
                aliases = {a.key: a.vehicle_id for a in PayerAlias.objects.filter(owner=request.user)}
                known = set(Remittance.objects.filter(vehicle__owner=request.user)
                            .exclude(receipt='').values_list('receipt', flat=True))
                rows, shown = [], []
                for r in parsed:
                    dup = bool(r['receipt']) and r['receipt'] in known
                    r['suggested'] = None if dup else mpesa.suggest(r, fleet, aliases)
                    r['dup'] = dup
                    rows.append({**r, 'date': r['date'].isoformat()})
                    shown.append({**r, 'i': len(shown)})
                request.session['statement_rows'] = [
                    {k: r[k] for k in ('receipt', 'date', 'details', 'amount', 'key')} for r in rows]
                return render(request, 'import_preview.html', {
                    'rows': shown, 'fleet': fleet,
                    'matched': sum(1 for r in shown if r['suggested']),
                    'dups': sum(1 for r in shown if r['dup']),
                })
        if not error:
            error = 'No incoming payments were found in that file.'
    elif request.method == 'POST':
        error = 'Choose a file first.'
    return render(request, 'import_upload.html', {'error': error})
