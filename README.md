# LightUpNet Carrier Management Portal

A self-hosted Django replacement for Springboard ASA — covering rates, DDI, finance, QoS, alerts, and graphs.

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+ (or use SQLite for local dev — see settings)
- Redis (for Celery task queue)

### 2. Install dependencies
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure the database
Edit `config/settings.py` and set your PostgreSQL credentials, **or** switch to SQLite by uncommenting the SQLite block and commenting out the PostgreSQL block.

### 4. Run migrations
```bash
python manage.py migrate
```

### 5. Create a superuser
```bash
python manage.py createsuperuser
```

### 6. Start the development server
```bash
python manage.py runserver
```

Open http://localhost:8000 — log in with the superuser you created.

---

## Project Structure

```
lightupnet/
├── config/           Django project config (settings, urls, wsgi)
├── apps/
│   ├── core/         Shared models: Company, Switch, Destination, DisconnectCause
│   ├── setup/        Admin: users, companies, interconnects, destinations
│   ├── rates/        Supplier & customer tariffs, rates, cost base
│   ├── ddi/          DDI numbers, profiles, routing
│   ├── finance/      Invoicing, bill verification, gross profit, payments
│   ├── qos/          CDRs, minutes analysis, CDR extract
│   ├── alerts/       Traffic alerts, alert rules
│   └── graphs/       Chart views: hourly, trends, world map
├── templates/        HTML templates (base.html, login.html, per-app)
└── static/           CSS, JS, images
```

## Module Overview

| Module   | Key models / features |
|----------|-----------------------|
| **Setup** | Company, Switch, Destination, DisconnectCause; system users |
| **Rates** | Tariff (buy/sell), Rate per prefix, CostBase; sell-to-buy comparison |
| **DDI** | DDINumber, DDIProfile, DDIRoute; loss analysis |
| **Finance** | Invoice, InvoiceLine, Payment, TermDeal, BillVerification |
| **QoS** | CDR (raw call records), MinuteSummary (hourly aggregates) |
| **Alerts** | AlertRule, AlertEvent; Celery-powered threshold checks |
| **Graphs** | Hourly minutes, GP trends, Top-10, World map (Chart.js) |

## CDR Ingestion

CDRs are expected to be loaded via either:
- The Django REST API endpoint (`/api/cdr/`) — POST JSON batches from your SBC
- A management command: `python manage.py import_cdrs <file.csv>`

(Both are stubs ready for implementation once the SBC format is confirmed.)

## Production Deployment

For production, replace SQLite/DEBUG with:
1. PostgreSQL connection string in `settings.py`
2. `DEBUG = False` + proper `ALLOWED_HOSTS`
3. `gunicorn config.wsgi:application` behind Nginx
4. Celery worker: `celery -A config worker -l info`
5. Celery beat: `celery -A config beat -l info`
