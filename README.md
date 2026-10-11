# Zamu

Daily remittance tracker for owners of matatus, boda bodas and taxis. Log what each driver hands over,
see who is behind, message them on WhatsApp, track fuel and repair costs, and rank vehicles by profit.

- **Today board:** every vehicle paid / short / not yet, with the running balance each driver owes.
- **Off days** don't count against the driver. Payments on any past day can be recorded; mistakes can be deleted.
- **Vehicle page:** 30-day table, costs, one-click WhatsApp message with the amount owed.
- **M-Pesa import:** upload a statement CSV; incoming payments are matched to vehicles by the driver's phone
  (full or masked) or name, you review, and receipts are never imported twice. Senders you assign are remembered.
  Try it with `samples/mpesa_statement_sample.csv`.
- **Report:** monthly collected vs expected, costs and net per vehicle, best to worst.

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo      # optional
.venv\Scripts\python manage.py runserver
.venv\Scripts\python manage.py test
```

Production: set `ZAMU_SECRET_KEY`, `ZAMU_DEBUG=0`, `ZAMU_HOSTS`, and `ZAMU_DB` (absolute path), then
`collectstatic`. Amounts are whole KES.
