# Change Log — v1.0 → v2.0 (AI Edition)

This file lists **every** change made to the original project, so the team can review, explain and, if needed, revert any part of it.

Guiding rule: the extension is **additive**. No original model field, URL or business rule was removed. The original database tables are unchanged (only new tables were added). A copy of the database before the extension is in `backups/db_before_ai_extension.sqlite3`.

---

## 1. New files

### 1.1 New Django app `analytics/`

| File | Purpose |
|------|---------|
| `analytics/apps.py` | App configuration; connects the signal handlers |
| `analytics/models.py` | 6 new models: `ProductionRecord`, `IncomingOrder`, `PredictionLog`, `MLModelVersion`, `APIKey`, `ExternalDataSnapshot` |
| `analytics/migrations/0001_initial.py` | Creates the 6 new tables (no change to existing tables) |
| `analytics/ml/features.py` | Feature engineering shared by training and inference (18 features) |
| `analytics/ml/synthetic.py` | Synthetic history generator + incoming-order payload generator |
| `analytics/ml/training.py` | Reads data via the API, compares 3 algorithms per model, saves and registers versions |
| `analytics/ml/service.py` | Inference service: model loading, self-healing, `predict_job`, `score_task`, `ingest_order` |
| `analytics/ml/insights.py` | KPIs, monthly trend, delay by category, material demand forecast |
| `analytics/ml/external.py` | Open API client (USD→RWF) with cache, DB snapshot and fallback |
| `analytics/api/auth.py` | API authentication/permission decorator and JSON envelope |
| `analytics/api/serializers.py` | Model → JSON conversion (salaries deliberately excluded) |
| `analytics/api/views.py`, `analytics/api/urls.py` | 16 REST endpoints (18 operations) under `/api/v1/` |
| `analytics/views.py`, `analytics/urls.py`, `analytics/forms.py` | Web pages under `/analytics/` |
| `analytics/dashboard.py` | Extra context for the main dashboard (fail-safe) |
| `analytics/signals.py` | Completed task → `ProductionRecord` (continuous learning) |
| `analytics/context_processors.py` | Live alert counts for the navbar bell |
| `analytics/templatetags/analytics_tags.py` | `{% task_risk %}` tag and filters (`risk_badge`, `pct`, `rwf`, `get_item`) |
| `analytics/admin.py` | Django Admin registration of the new models |
| `analytics/tests.py` | 40 automated tests |
| `analytics/management/commands/*.py` | `setup_ai`, `generate_synthetic_data`, `train_models`, `simulate_orders`, `create_api_key` |
| `analytics/templates/analytics/*.html` | 7 templates: insights, order detail, predictor, model center, history, API center, prediction partial |
| `analytics/static/analytics/analytics.css` | Styles of the new widgets (light and dark mode) |
| `analytics/ml_models/*.joblib` | Trained model files (v1–v3; v3 is active) |

### 1.2 Other new files

| File | Purpose |
|------|---------|
| `docs/Group_13_Final_Project_Report.pdf` / `.docx` | Final project report |
| `docs/CHANGES.md` | This file |
| `docs/screenshots/*.png` | Screenshots used in the report |
| `backups/db_before_ai_extension.sqlite3` | Original database, untouched |

---

## 2. Modified files

| File | Change | Why |
|------|--------|-----|
| `config/settings.py` | Added `'analytics'` to `INSTALLED_APPS`; added context processor `analytics.context_processors.nav_alerts`; added `ML_MODEL_DIR`, `AI_EXTERNAL_APIS_ENABLED`, `AI_FALLBACK_USD_RWF` and `LOGGING` | Register the new module |
| `config/urls.py` | Added `path('analytics/', ...)` and `path('api/v1/', ...)` | New pages and API |
| `production/views.py` | `dashboard()` now merges `analytics.dashboard.dashboard_context()` inside a `try/except` | Dashboard AI widgets; the original dashboard still renders if the AI layer fails |
| `production/models.py` | Tracks `_original_due`; the "due date cannot be in the past" rule now applies only to **new tasks or changed due dates** | **Bug fix** (see 3.1) |
| `templates/base.html` | Loads `analytics.css`; new sidebar section *AI & ANALYTICS* (5 links); bell shows real counts and links to the Alerts Center; *Quick Add* has an AI What-if link; footer version 2.0.0 | Navigation and alerts |
| `templates/dashboard.html` | All original widgets kept; added KPI row, Delay-Risk Monitor, task-status chart, live order feed (auto-refresh), material demand forecast, trend and category charts; HR links shown only to staff | Enhanced dashboard + UX fix (3.2) |
| `production/templates/production/task_detail.html` | Added *AI Risk Assessment* card; *Edit Task* button shown only to staff | AI feature + UX fix (3.3) |
| `requirements.txt` | Re-saved as **UTF-8** (it was UTF-16); added `numpy`, `scipy`, `scikit-learn`, `joblib` | ML dependencies; UTF-16 can break `pip` on some systems |
| `readme.md` | Rewritten for v2.0 (original content preserved) | Documentation |

No other original file was modified.

---

## 3. Fixes to existing behaviour

### 3.1 Overdue tasks could not be updated (bug)
**Before:** `ProductionTask.clean()` refused any save when `due_date < today` and status ≠ Completed. Once a task became overdue, a manager could no longer record progress (e.g. 3 → 5 units) without also moving the due date.
**After:** the rule only applies when the task is new or its due date is changed. Creating a task with a past date, or moving a due date into the past, is still refused.
Covered by tests `test_fix_overdue_task_progress_can_be_updated` and `test_original_rule_new_task_cannot_have_past_due_date`.

### 3.2 Read-only users were sent to pages they cannot open (UX)
The dashboard showed *View Roster*, *View All Artisans* and artisan-name links to read-only users; clicking them silently redirected back to the dashboard. They are now shown only to staff.

### 3.3 *Edit Task* button visible to read-only users (UX)
Same issue on the task detail page; the button is now staff-only.

### 3.4 Notification bell always showed "!" (UX)
It now shows the real number of overdue tasks + low-stock materials + high-risk incoming orders, with a breakdown.

---

## 4. Data changes in `db.sqlite3`

| Change | Detail |
|--------|--------|
| 6 new tables | Created by `analytics/migrations/0001_initial.py` |
| 2,000 synthetic `ProductionRecord` rows | Training history generated from the real catalogue (seed 42) |
| 3 live `ProductionRecord` rows | The 3 completed real tasks (TSK-13, 17, 20) imported into the history |
| 6 `MLModelVersion` rows | v1, v2, v3 of each model (v3 active) |
| 18 `IncomingOrder` rows | Demo orders created by the simulator and API tests |
| **3 new production tasks** (TSK-23, 24, 25) | Created by converting 3 low-risk orders through the normal workflow; materials were deducted by the original stock rules. TSK-25 was set *In Progress* (3/9) |
| User `ml-service` | Internal service account (unusable password, not staff) used when training reads the API in-process. It cannot log in |

To return to the original data: copy `backups/db_before_ai_extension.sqlite3` over `db.sqlite3`, then run `python manage.py migrate` and `python manage.py setup_ai`.

---

## 5. Not included in the zip
* `venv/` – it was a Windows virtual environment without the new packages. Re-create it with `python -m venv venv` and `pip install -r requirements.txt`.
* `__pycache__/` folders – regenerated automatically by Python.

The `.git` folder is included unchanged. The new work is **not committed**; review it with `git status` and commit it (e.g. on a branch `feature/ai-analytics`).
