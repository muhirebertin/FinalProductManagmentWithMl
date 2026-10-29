# analytics/ml/training.py
"""
Training pipeline.

1. READ the training data from the REST API (/api/v1/records/), either
   - in-process, through Django's full request/response stack (default), or
   - over HTTP from a running server (`--api-url` + `--api-key`).
2. Engineer features (analytics.ml.features).
3. Split by time: the oldest 80 % of batches train, the newest 20 % test.
4. Compare three algorithms per task and keep the best one:
     classifier (delayed yes/no) -> selected by ROC-AUC
     regressor  (actual days)    -> selected by MAE
5. Refit the winner on all data, save it with joblib, and register a new
   version in the MLModelVersion table (older versions are deactivated).
"""
import json
import logging
import math
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
import sklearn
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from sklearn.ensemble import (GradientBoostingClassifier, GradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score, recall_score,
                             roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import features as F

logger = logging.getLogger("analytics")
_TRAIN_LOCK = threading.Lock()

API_RECORDS_PATH = "/api/v1/records/"
PAGE_SIZE = 1000


class TrainingError(Exception):
    pass


def model_dir() -> Path:
    path = Path(getattr(settings, "ML_MODEL_DIR", Path(settings.BASE_DIR) / "analytics" / "ml_models"))
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# 1. Data acquisition through the API
# ---------------------------------------------------------------------------
def get_service_user():
    """
    Internal read-only service account used when the training pipeline calls
    the API in-process. It has an unusable password, so nobody can log in
    with it, and it is not staff.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="ml-service",
        defaults={"is_staff": False, "is_superuser": False, "is_active": True,
                  "first_name": "ML", "last_name": "Service"},
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user


def _internal_host():
    for host in getattr(settings, "ALLOWED_HOSTS", []) or []:
        if host and host != "*":
            return host.lstrip(".") or "localhost"
    return "localhost"


def fetch_records_inprocess():
    """Read every record page from the API using Django's test client."""
    from django.test import Client
    client = Client(HTTP_HOST=_internal_host())
    client.force_login(get_service_user())
    records, page = [], 1
    while True:
        response = client.get(API_RECORDS_PATH, {"page": page, "page_size": PAGE_SIZE})
        if response.status_code != 200:
            raise TrainingError(f"API returned HTTP {response.status_code}: {response.content[:200]!r}")
        body = response.json()
        records.extend(body["data"])
        if page >= body["meta"]["pages"]:
            break
        page += 1
    client.logout()
    return records


def fetch_records_http(api_url, api_key, timeout=30):
    """Read every record page from a running server over HTTP."""
    base = api_url.rstrip("/")
    records, page = [], 1
    while True:
        query = urllib.parse.urlencode({"page": page, "page_size": PAGE_SIZE})
        req = urllib.request.Request(f"{base}{API_RECORDS_PATH}?{query}",
                                     headers={"X-API-Key": api_key or "", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TrainingError(f"API returned HTTP {exc.code}. Check the API key.") from exc
        except urllib.error.URLError as exc:
            raise TrainingError(f"Cannot reach {base}: {exc.reason}. Is the server running?") from exc
        records.extend(body["data"])
        if page >= body["meta"]["pages"]:
            break
        page += 1
    return records


def fetch_records(api_url=None, api_key=None):
    if api_url:
        return fetch_records_http(api_url, api_key), f"api-http ({api_url})"
    return fetch_records_inprocess(), "api-inprocess"


# ---------------------------------------------------------------------------
# 2. Candidate algorithms
# ---------------------------------------------------------------------------
def classifier_candidates():
    return {
        "Logistic Regression": lambda: Pipeline([
            ("vec", DictVectorizer(sparse=False)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=3000, class_weight="balanced")),
        ]),
        "Random Forest": lambda: Pipeline([
            ("vec", DictVectorizer(sparse=False)),
            ("model", RandomForestClassifier(n_estimators=250, min_samples_leaf=3,
                                             class_weight="balanced_subsample",
                                             random_state=42, n_jobs=1)),
        ]),
        "Gradient Boosting": lambda: Pipeline([
            ("vec", DictVectorizer(sparse=False)),
            ("model", GradientBoostingClassifier(n_estimators=250, learning_rate=0.05,
                                                 max_depth=3, random_state=42)),
        ]),
    }


def regressor_candidates():
    return {
        "Ridge Regression": lambda: Pipeline([
            ("vec", DictVectorizer(sparse=False)),
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=1.0)),
        ]),
        "Random Forest": lambda: Pipeline([
            ("vec", DictVectorizer(sparse=False)),
            ("model", RandomForestRegressor(n_estimators=250, min_samples_leaf=2,
                                            random_state=42, n_jobs=1)),
        ]),
        "Gradient Boosting": lambda: Pipeline([
            ("vec", DictVectorizer(sparse=False)),
            ("model", GradientBoostingRegressor(n_estimators=300, learning_rate=0.05,
                                                max_depth=3, random_state=42)),
        ]),
    }


def feature_importances(pipe):
    """Importance per *original* feature (one-hot columns are summed back)."""
    names = pipe.named_steps["vec"].feature_names_
    model = pipe.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        raw = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        raw = np.abs(np.ravel(model.coef_)).astype(float)
    else:
        return []
    grouped = defaultdict(float)
    for name, value in zip(names, raw):
        grouped[name.split("=")[0]] += float(value)
    total = sum(grouped.values()) or 1.0
    items = sorted(grouped.items(), key=lambda kv: kv[1], reverse=True)
    return [{"feature": k, "importance": round(v / total, 4),
             "description": F.FEATURE_DESCRIPTIONS.get(k, k)} for k, v in items]


def _positive_proba(pipe, X):
    classes = list(pipe.classes_)
    return pipe.predict_proba(X)[:, classes.index(1)]


def evaluate_classifier(pipe, X_test, y_test):
    proba = _positive_proba(pipe, X_test)
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()
    return {
        "accuracy": round(accuracy_score(y_test, pred), 4),
        "precision": round(precision_score(y_test, pred, zero_division=0), 4),
        "recall": round(recall_score(y_test, pred, zero_division=0), 4),
        "f1": round(f1_score(y_test, pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_test, proba), 4) if len(set(y_test)) > 1 else None,
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "delay_rate_test": round(float(np.mean(y_test)), 4),
    }


def evaluate_regressor(pipe, X_test, y_test):
    pred = np.clip(pipe.predict(X_test), 0.5, None)
    y = np.asarray(y_test, dtype=float)
    ape = np.abs(pred - y) / np.maximum(y, 0.5)
    return {
        "mae": round(float(mean_absolute_error(y, pred)), 3),
        "rmse": round(float(math.sqrt(mean_squared_error(y, pred))), 3),
        "r2": round(float(r2_score(y, pred)), 4),
        "median_ape": round(float(np.median(ape)) * 100, 2),
        "within_20pct": round(float(np.mean(ape <= 0.20)) * 100, 2),
    }


# ---------------------------------------------------------------------------
# 3. Training entry point
# ---------------------------------------------------------------------------
def _time_split(X, y_a, y_b, dates, test_fraction=0.2):
    order = sorted(range(len(X)), key=lambda i: dates[i])
    cut = max(1, int(len(order) * (1 - test_fraction)))
    tr, te = order[:cut], order[cut:]
    pick = lambda seq, idx: [seq[i] for i in idx]  # noqa: E731
    return (pick(X, tr), pick(X, te), pick(y_a, tr), pick(y_a, te), pick(y_b, tr), pick(y_b, te),
            dates[order[cut]] if te else None)


def _register(name, algorithm, pipe, metrics, candidates, importances, n_train, n_test, source, trained_by):
    from analytics.models import MLModelVersion
    last = MLModelVersion.objects.filter(name=name).order_by("-version").first()
    version = (last.version + 1) if last else 1
    file_name = f"{name}_v{version}.joblib"
    joblib.dump({"pipeline": pipe, "sklearn_version": sklearn.__version__,
                 "name": name, "version": version, "algorithm": algorithm},
                model_dir() / file_name)
    with transaction.atomic():
        MLModelVersion.objects.filter(name=name, is_active=True).update(is_active=False)
        obj = MLModelVersion.objects.create(
            name=name, version=version, algorithm=algorithm, file_name=file_name,
            metrics=metrics, candidates=candidates, feature_importances=importances,
            n_train=n_train, n_test=n_test, data_source=source,
            sklearn_version=sklearn.__version__, is_active=True, trained_by=trained_by,
            trained_at=timezone.now(),
        )
    return obj


def train_models(api_url=None, api_key=None, trained_by="system", min_records=60):
    """Train both models. Returns a summary dictionary."""
    if not _TRAIN_LOCK.acquire(blocking=False):
        raise TrainingError("A training run is already in progress. Please wait.")
    try:
        started = timezone.now()
        records, source = fetch_records(api_url, api_key)
        if len(records) < min_records:
            raise TrainingError(f"Only {len(records)} records available; at least {min_records} are needed. "
                                f"Run 'python manage.py generate_synthetic_data' first.")
        X, y_delay, y_days, dates = F.build_training_rows(records)
        X_tr, X_te, yc_tr, yc_te, yr_tr, yr_te, split_date = _time_split(X, y_delay, y_days, dates)
        if len(set(yc_tr)) < 2:
            raise TrainingError("Training data contains only one outcome class (all delayed or all on time).")

        summary = {"records": len(records), "source": source, "n_train": len(X_tr), "n_test": len(X_te),
                   "split_date": split_date.isoformat() if split_date else None}

        # --- classifier ---
        cls_scores, best = [], None
        for algo, make in classifier_candidates().items():
            pipe = make().fit(X_tr, yc_tr)
            m = evaluate_classifier(pipe, X_te, yc_te)
            cls_scores.append({"algorithm": algo, **{k: m[k] for k in ("accuracy", "f1", "roc_auc")}})
            score = m["roc_auc"] if m["roc_auc"] is not None else m["f1"]
            if best is None or score > best[0]:
                best = (score, algo, m)
        _, algo, metrics = best
        final = classifier_candidates()[algo]().fit(X, y_delay)
        cls = _register("delay_classifier", algo, final, metrics, cls_scores, feature_importances(final),
                        len(X_tr), len(X_te), source, trained_by)
        summary["delay_classifier"] = {"version": cls.version, "algorithm": algo, "metrics": metrics,
                                       "candidates": cls_scores}

        # --- regressor ---
        reg_scores, best = [], None
        for algo, make in regressor_candidates().items():
            pipe = make().fit(X_tr, yr_tr)
            m = evaluate_regressor(pipe, X_te, yr_te)
            reg_scores.append({"algorithm": algo, **{k: m[k] for k in ("mae", "rmse", "r2")}})
            if best is None or m["mae"] < best[0]:
                best = (m["mae"], algo, m)
        _, algo, metrics = best
        final = regressor_candidates()[algo]().fit(X, y_days)
        reg = _register("duration_regressor", algo, final, metrics, reg_scores, feature_importances(final),
                        len(X_tr), len(X_te), source, trained_by)
        summary["duration_regressor"] = {"version": reg.version, "algorithm": algo, "metrics": metrics,
                                         "candidates": reg_scores}

        summary["seconds"] = round((timezone.now() - started).total_seconds(), 2)
        F.invalidate_history_cache()
        from .service import predictor
        predictor.clear_cache()
        logger.info("Training finished: %s", summary)
        return summary
    finally:
        _TRAIN_LOCK.release()

