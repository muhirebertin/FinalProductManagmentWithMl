# Production Management System — AI Edition (v2.0)

A database-driven **Production Management System (ERP)** built for a leather manufacturing enterprise (Le Mieux Ltd) using Python, Django and the AdminLTE dashboard framework.

Version 2.0 adds an **AI & Analytics** module: a REST API, machine-learning models trained on data read through that API, live scoring of new incoming orders, an enhanced dashboard and an Open API integration. All version 1.0 features work exactly as before.

> Full documentation: `docs/Group_13_Final_Project_Report.pdf` (also provided as `.docx`).
> Every change made to the original code is listed in `docs/CHANGES.md`.

---

## Core Features (v1.0)

1. **Active Workload Dashboard:** real-time summary cards, overdue task alerts and an artisan workload radar.
2. **Dynamic BOM & Cost Prediction:** links products to raw materials via inline formsets and calculates production cost and profit margin.
3. **Automated Inventory Stock Control:** checks the Bill of Materials (BOM) against warehouse stock when a task is created, then deducts or refunds materials automatically.
4. **Human Resources (HR) Management:** artisans, contracts and leave requests. Managers cannot assign tasks to staff on approved leave.
5. **State Machine & Validation:** strict workflow rules (e.g. tasks with progress cannot be "Pending"; completed tasks must match the target quantity). `ProtectedError` is handled gracefully.
6. **Modern UI & UX:** DataTables (search, sort, pagination), persistent Dark/Light mode and shared components.

## New in v2.0 — AI & Analytics

| # | Feature | Where |
|---|---------|-------|
| 1 | **REST API v1** (16 endpoints / 18 operations, JSON, API-key + session auth, staff-only writes) | `/api/v1/`, docs in **API Center** |
| 2 | **Training data**: 2,000 synthetic batches generated from the *real* catalogue + real completed tasks | **Production History** |
| 3 | **Models trained on data read through the API** (in-process or over HTTP); 3 algorithms compared per model | `python manage.py train_models` |
| 4 | **Deployed in Django**: versioned model registry, joblib artefacts, self-healing retraining | **Model Center** |
| 5 | **Live predictions on incoming data**: every new order is scored on arrival (delay risk, duration, best artisan, stock check, advice) | **AI Insights & Orders**, dashboard |
| 6 | **Enhanced dashboard**: KPI row, delay-risk monitor, live order feed (auto-refresh), material demand forecast, 3 charts | `/` |
| 7 | **What-if Predictor**: simulate a job before committing to it | **What-if Predictor** |
| 8 | **Open API**: live USD→RWF exchange rate (open.er-api.com) with offline fallback | Dashboard, `/api/v1/external/fx/` |
| 9 | **Continuous learning**: completed tasks are added to the training data automatically | `analytics/signals.py` |
| 10 | **AI risk card** on every production task | Task detail page |
| 11 | **Live alert bell** with real counts (overdue, low stock, high-risk orders) | Top navbar |
| 12 | **40 automated tests** (new features + regression tests of the original rules) | `python manage.py test` |

**Current model quality** (evaluated on the newest 20 % of batches, never seen in training):

| Model | Algorithm (selected) | Key metrics |
|-------|----------------------|-------------|
| Delay-risk classifier | Gradient Boosting | ROC-AUC **0.934**, accuracy 85.5 %, F1 0.78 |
| Duration regressor | Gradient Boosting | R² **0.893**, MAE **1.70 days** |

---

## Tech Stack

* **Backend:** Python 3.12+, Django 6.1
* **Machine learning:** scikit-learn, NumPy, SciPy, joblib
* **Frontend:** HTML5, CSS3, Bootstrap 4, AdminLTE 3, Font Awesome, Chart.js 2.9, DataTables
* **Database:** SQLite
* **External Open API:** ExchangeRate-API open access endpoint (no key needed)

---

## Project Structure

```text
production_management/
├── config/               # Settings, root URLs, WSGI/ASGI
├── employees/            # Artisans, departments, contracts, leave requests
├── inventory/            # Raw materials, products, Bills of Materials
├── production/           # Production tasks, dashboard view, alerts
├── analytics/            # NEW - AI & Analytics module
│   ├── api/              #   REST API: auth.py, serializers.py, views.py, urls.py
│   ├── ml/               #   features, synthetic, training, service (inference), insights, external (Open API)
│   ├── management/commands/   setup_ai, generate_synthetic_data, train_models, simulate_orders, create_api_key
│   ├── ml_models/        #   trained model files (*.joblib)
│   ├── templates/analytics/   insights, predictor, model center, history, API center, order detail
│   ├── static/analytics/ #   analytics.css
│   ├── templatetags/     #   {% task_risk %} and formatting filters
│   ├── models.py         #   ProductionRecord, IncomingOrder, PredictionLog, MLModelVersion, APIKey, ExternalDataSnapshot
│   ├── signals.py        #   completed task -> training record
│   ├── dashboard.py      #   extra dashboard context
│   └── tests.py          #   40 automated tests
├── templates/            # base.html, dashboard.html, shared components, login
├── static/               # AdminLTE assets and plugins
├── docs/                 # Final report (PDF + DOCX), CHANGES.md, screenshots
├── backups/              # Copy of the database before the AI extension
├── db.sqlite3            # Database (ready to use: data + trained models registered)
├── requirements.txt
├── Credentials           # Login accounts
└── manage.py
```

---

## Getting Started

Open a terminal in the project folder (where `manage.py` is).

1. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate          # Windows
   source venv/bin/activate       # macOS / Linux
   ```
2. **Install the dependencies** (Django + scikit-learn, NumPy, SciPy, joblib)
   ```bash
   pip install -r requirements.txt
   ```
3. **Apply the migrations** (the shipped database is already migrated; this is safe to run)
   ```bash
   python manage.py migrate
   ```
4. **(Optional) Rebuild the AI module from scratch** – regenerates the synthetic history, retrains the models through the API and creates 8 demo orders. The shipped database already contains all of this.
   ```bash
   python manage.py setup_ai --force
   ```
5. **(Optional) Run the tests**
   ```bash
   python manage.py test
   ```
6. **Start the server**
   ```bash
   python manage.py runserver
   ```
7. Open **http://127.0.0.1:8000/** and log in.

| Username | Password | Role |
|----------|----------|------|
| `admin` | `Admin@2026` | Superuser – everything, including Django Admin |
| `HR1` | `Web@tech2` | Manager (staff) – all CRUD, convert orders, retrain models, API keys |
| `User` | `Web@tech3` | Viewer – read-only pages and read-only API, What-if Predictor |

> **First start on another computer:** if your scikit-learn version differs from the one used to train the shipped models, the system detects it and **retrains automatically** on the first prediction (about 10 seconds). Nothing needs to be done manually.

---

## Demonstrating the AI features (5-minute script)

1. **Dashboard** (`admin`): new KPI row, Delay-Risk Monitor, Live Incoming Orders, Material Demand Forecast, charts.
2. Click **Simulate orders** on the Live Incoming Orders card: 3 orders arrive through the ingestion pipeline and are scored instantly.
3. **AI Insights & Orders**: filter by risk, open an order to see the full prediction, artisan ranking and stock check, then **Create task** (the original stock and leave rules still apply).
4. **What-if Predictor**: pick a product, quantity and due date; leave the artisan empty to let the AI choose.
5. **Model Center**: metrics, confusion matrix, algorithm comparison, feature importance; click **Retrain models now**.
6. **Real-time stream through the API** (second terminal, server running):
   ```bash
   python manage.py create_api_key --user HR1 --name "Simulator"
   python manage.py simulate_orders --count 20 --interval 4 --api-url http://127.0.0.1:8000 --api-key <KEY>
   ```
   Watch new rows appear on the dashboard (it checks every 15 seconds).
7. **Training from the API over HTTP**:
   ```bash
   python manage.py train_models --api-url http://127.0.0.1:8000 --api-key <KEY>
   ```

---

## Management Commands

| Command | Purpose |
|---------|---------|
| `python manage.py setup_ai [--force] [--orders 8]` | One-shot setup: training data, import completed tasks, train, demo orders |
| `python manage.py generate_synthetic_data [--records 2000] [--days 540] [--seed 42] [--keep]` | (Re)generate the synthetic history |
| `python manage.py train_models [--api-url URL --api-key KEY]` | Read data from the API, compare algorithms, deploy new model versions |
| `python manage.py simulate_orders [--count 10] [--interval 3] [--api-url URL --api-key KEY]` | Stream new incoming orders (`--count 0` = until Ctrl+C) |
| `python manage.py create_api_key --user USERNAME [--name LABEL]` | Create an API key (printed once) |

## REST API (summary)

Base URL `http://127.0.0.1:8000/api/v1/` – authenticate with header `X-API-Key: <key>` or a logged-in session.

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/` , `/health/` | Index, status | public |
| GET | `/products/`, `/materials/`, `/employees/`, `/tasks/` | Catalogue, stock, artisans, tasks | read |
| GET | `/tasks/<id>/prediction/` | AI assessment of a task | read |
| GET / POST | `/records/` | Training data (paginated) / push a finished batch | read / staff |
| GET / POST | `/orders/` | Incoming orders / **ingest a new order (scored instantly)** | read / staff |
| GET | `/orders/<id>/` | Order with its full prediction | read |
| POST | `/predict/` | Stateless what-if prediction | read |
| GET / POST | `/model/`, `/model/retrain/` | Model registry / retrain | read / staff |
| GET | `/dashboard/summary/`, `/forecast/materials/`, `/external/fx/` | Analytics, forecast, Open API rate | read |

Full documentation with examples: **API Center** page (`/analytics/api/`).

## Configuration (config/settings.py)

| Setting | Default | Meaning |
|---------|---------|---------|
| `ML_MODEL_DIR` | `analytics/ml_models` | Where model files are stored |
| `AI_EXTERNAL_APIS_ENABLED` | `True` | Set `False` to never call the Open API (fully offline) |
| `AI_FALLBACK_USD_RWF` | `1450.0` | Exchange rate used if the Open API has never been reachable |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: sklearn` | `pip install -r requirements.txt` inside the activated venv |
| First AI page takes ~10 s | Normal once: models are retrained for your scikit-learn version |
| Exchange rate shows *offline* | No internet: the last known or fallback rate is used; everything else works |
| Simulator says *Cannot reach ...* | Start `python manage.py runserver` first, or omit `--api-url` to run in-process |
| `401 invalid_api_key` | Key mistyped or revoked: create a new one in **API Center** |
| `403 permission_denied` on POST | The key belongs to a non-staff user; use a manager's key |

---

## Group Members
* **Iradukunda Muhire Bertin** (20251MBI046)
* **Isaac Nkusi** (20251MBI020)
* **Rwabukanga Jean de Dieu** (20251MBI010)

*Big Data Analytics, Adventist University of Central Africa (AUCA).*
