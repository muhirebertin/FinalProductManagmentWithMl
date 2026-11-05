# Production Management System

A web-based ERP for Le Mieux Ltd, a leather manufacturer. It brings production, inventory and HR into one place, and uses machine learning to warn managers about late jobs before they happen.

Built with Python, Django and the AdminLTE dashboard.

## What it does

- **Production planning:** create tasks, track progress and get overdue alerts. Status rules are enforced, for example a task with progress cannot stay "Pending".
- **Costing:** each product has a Bill of Materials, and the system calculates its production cost and profit margin.
- **Stock control:** a task is accepted only if the warehouse has enough material. Stock is deducted when a task is created and refunded if it is reduced or deleted.
- **HR:** artisans, contracts and leave requests. Staff on approved leave cannot be assigned work.
- **Delay and duration prediction:** every new order is scored when it arrives, giving a delay risk, an expected duration, the best available artisan, a stock check and short advice.
- **Dashboard:** KPIs, a delay-risk monitor for open tasks, a live order feed that refreshes every 15 seconds, a material demand forecast and charts.
- **What-if Predictor:** test a job before committing to it.
- **REST API:** 16 endpoints under `/api/v1/` with API-key or session authentication.
- **Exchange rate:** the live USD to RWF rate is read from a public API, with an offline fallback.

## Models

Two models are trained on production history read through the API. The history is 2,000 synthetic batches built from the real products, recipes and artisans, plus completed tasks. Finished tasks are added automatically, so the models can be retrained on real data over time.

| Model | Algorithm | Result on unseen data |
|-------|-----------|-----------------------|
| Delay-risk classifier | Gradient Boosting | ROC-AUC 0.934, accuracy 85.5% |
| Duration regressor | Gradient Boosting | R² 0.893, mean error 1.70 days |

If a model file is missing or was saved with a different scikit-learn version, the system retrains it automatically (about 10 seconds).

## Tech stack

- Python 3.12+, Django 6.1
- scikit-learn, NumPy, SciPy, joblib
- Bootstrap 4, AdminLTE 3, Chart.js, DataTables
- SQLite

## Project structure

```text
config/        Settings and root URLs
employees/     Artisans, contracts, leave requests
inventory/     Raw materials, products, Bills of Materials
production/    Tasks, dashboard, alerts
analytics/     REST API, ML pipeline, order scoring, AI pages
  api/         Authentication, serializers, endpoints
  ml/          Features, training, inference, insights
templates/     Shared layouts and login page
static/        AdminLTE assets
docs/          Report and screenshots
db.sqlite3     Ready-to-use database
```

## Getting started

Run these from the folder that contains `manage.py`.

```bash
python -m venv venv
venv\Scripts\activate            # Windows
source venv/bin/activate         # macOS / Linux

pip install -r requirements.txt
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in:

| Username | Password | Role |
|----------|----------|------|
| `admin` | `Admin@2026` | Superuser, full access and Django Admin |
| `HR1` | `Web@tech2` | Manager: edit data, convert orders, retrain models, manage API keys |
| `User` | `Web@tech3` | Viewer: read-only, can use the What-if Predictor |

These accounts are for local demonstration only. Change them before any real deployment.

## Quick demo

1. Sign in as `admin` and look at the dashboard.
2. Click **Simulate orders** on the Live Incoming Orders card. New orders appear and are scored immediately.
3. Open **AI Insights & Orders**, pick an order and review its prediction, then click **Create task**.
4. Try the **What-if Predictor** with any product, quantity and due date.
5. Open the **Model Center** to see the metrics, then retrain with one click.

To stream orders through the API from a second terminal while the server is running:

```bash
python manage.py create_api_key --user HR1 --name "Simulator"
python manage.py simulate_orders --count 20 --interval 4 --api-url http://127.0.0.1:8000 --api-key <KEY>
```

## Useful commands

| Command | Purpose |
|---------|---------|
| `python manage.py test` | Run the 40 automated tests |
| `python manage.py setup_ai --force` | Rebuild the training data, retrain the models and create demo orders |
| `python manage.py train_models [--api-url URL --api-key KEY]` | Retrain from the API |
| `python manage.py simulate_orders [--count N --interval S]` | Stream sample orders |
| `python manage.py create_api_key --user NAME` | Create an API key (shown once) |

## REST API

Base URL: `http://127.0.0.1:8000/api/v1/`. Send the key as `X-API-Key: <key>`, or use a signed-in session. Reads are open to any authenticated user, writes need a staff account. Full documentation with examples is on the **API Center** page.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/`, `/health/` | Index and status (public) |
| GET | `/products/`, `/materials/`, `/employees/`, `/tasks/` | Catalogue, stock, artisans, tasks |
| GET | `/tasks/<id>/prediction/` | Risk assessment of a task |
| GET, POST | `/records/` | Training data, or push a finished batch |
| GET, POST | `/orders/` | List orders, or submit a new one (scored instantly) |
| GET | `/orders/<id>/` | One order with its full prediction |
| POST | `/predict/` | What-if prediction, nothing stored |
| GET, POST | `/model/`, `/model/retrain/` | Model info, or retrain |
| GET | `/dashboard/summary/`, `/forecast/materials/`, `/external/fx/` | Analytics and exchange rate |

## Configuration

Set in `config/settings.py`:

| Setting | Default | Meaning |
|---------|---------|---------|
| `ML_MODEL_DIR` | `analytics/ml_models` | Where model files are stored |
| `AI_EXTERNAL_APIS_ENABLED` | `True` | Set to `False` to run fully offline |
| `AI_FALLBACK_USD_RWF` | `1450.0` | Rate used when the exchange API has never been reachable |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: sklearn` | Activate the virtual environment and run `pip install -r requirements.txt` |
| First AI page is slow | Normal once; the models retrain for your scikit-learn version |
| Exchange rate shows "offline" | No internet. The last known or fallback rate is used |
| Simulator cannot reach the server | Start `runserver` first, or leave out `--api-url` |
| `401 invalid_api_key` | The key is wrong or revoked. Create a new one in API Center |
| `403 permission_denied` on POST | The key belongs to a non-staff user. Use a manager's key |

## Team

Group 13, Big Data Analytics, Adventist University of Central Africa (AUCA)

- Iradukunda Muhire Bertin (20251MBI046)
- Isaac Nkusi (20251MBI020)
- Rwabukanga Jean de Dieu (20251MBI010)
