"""Read an M-Pesa statement CSV and work out which vehicle each payment belongs to.

Safaricom statements have junk lines above the table and columns such as Receipt No,
Completion Time, Details, Transaction Status, Paid In, Withdrawn, Balance. Details of an
incoming payment look like "Funds received from 254712345678 - JOHN OTIENO", sometimes with
the phone masked ("2547***678" / "0712***678"). Other bank/till exports with a date,
details and an amount column also work.
"""
import csv
import io
import re
from datetime import datetime

DATE_FORMATS = ['%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
                '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d %b %Y']

RECEIPT = ('receipt no', 'receipt no.', 'receipt', 'transaction id', 'transaction code', 'reference')
WHEN = ('completion time', 'date', 'time', 'transaction date', 'completion date')
DETAILS = ('details', 'description', 'narration', 'transaction details', 'particulars')
PAID_IN = ('paid in', 'credit', 'amount in', 'money in', 'received')
AMOUNT = ('amount',)
STATUS = ('transaction status', 'status')

FULL_PHONE = re.compile(r'(?<!\d)(?:\+?254|0)?([17]\d{8})(?!\d)')
MASKED_PHONE = re.compile(r'(?<!\d)(?:\+?254|0)?([17]\d{1,3})\*+(\d{2,4})(?!\d)')


class StatementError(Exception):
    pass


def _find(header, names):
    for i, h in enumerate(header):
        if h in names:
            return i
    return None


def _number(text):
    text = (text or '').replace(',', '').replace('KES', '').replace('Ksh', '').strip()
    try:
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


def _date(text):
    text = (text or '').strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def sender_key(details):
    """A stable identity for the payer: a full phone number, a masked phone, or the name."""
    m = FULL_PHONE.search(details)
    if m:
        return '254' + m.group(1)
    m = MASKED_PHONE.search(details)
    if m:
        return f'254{m.group(1)}*{m.group(2)}'
    name = details.split(' - ', 1)[1] if ' - ' in details else details
    name = re.sub(r'[^A-Za-z ]', ' ', name).upper().strip()
    return 'NAME:' + ' '.join(name.split())


def parse(raw):
    """Returns list of dicts: receipt, date (date), details, amount (int KES), key."""
    text = raw.decode('utf-8-sig', errors='replace') if isinstance(raw, bytes) else raw
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    header_at = None
    for n, row in enumerate(rows):
        cells = [c.strip().lower() for c in row]
        if _find(cells, DETAILS) is not None and (_find(cells, WHEN) is not None
                                                  or _find(cells, RECEIPT) is not None):
            header_at = n
            break
    if header_at is None:
        raise StatementError('Could not find the table. It needs at least Details and Date/Receipt columns.')
    header = [c.strip().lower() for c in rows[header_at]]
    i_receipt, i_when, i_details = _find(header, RECEIPT), _find(header, WHEN), _find(header, DETAILS)
    i_in, i_amount, i_status = _find(header, PAID_IN), _find(header, AMOUNT), _find(header, STATUS)
    if i_in is None and i_amount is None:
        raise StatementError('No "Paid In" or "Amount" column found.')
    out = []
    for row in rows[header_at + 1:]:
        if not any(c.strip() for c in row) or len(row) <= (i_details or 0):
            continue

        def cell(i):
            return row[i].strip() if i is not None and i < len(row) else ''

        if i_status is not None and cell(i_status) and 'complete' not in cell(i_status).lower():
            continue
        amount = _number(cell(i_in)) if i_in is not None else _number(cell(i_amount))
        when = _date(cell(i_when))
        if amount <= 0 or when is None:
            continue
        details = cell(i_details)
        out.append({'receipt': cell(i_receipt), 'date': when, 'details': details,
                    'amount': int(round(amount)), 'key': sender_key(details)})
    return out


def _driver_matches_key(vehicle, key):
    phone = vehicle.driver_phone
    if not phone or key.startswith('NAME:'):
        return False
    if '*' not in key:
        return phone == key
    head, tail = key[3:].split('*')  # after '254'
    return phone[3:].startswith(head) and phone.endswith(tail)


def suggest(row, vehicles, aliases):
    """Pick a vehicle for a payment row: remembered payer, driver phone, then unique name match."""
    if row['key'] in aliases:
        return aliases[row['key']]
    hits = [v for v in vehicles if _driver_matches_key(v, row['key'])]
    if len(hits) == 1:
        return hits[0].pk
    details = row['details'].upper()
    named = [v for v in vehicles
             if any(len(t) >= 4 and t in details for t in v.driver_name.upper().split())]
    return named[0].pk if len(named) == 1 else None
