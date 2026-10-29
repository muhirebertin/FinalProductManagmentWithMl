# analytics/tests.py
"""
Automated tests for the AI & Analytics extension AND regression tests proving
that the original business rules still work.

Run:  python manage.py test
"""
import datetime as dt
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from employees.models import Contract, Department, Employee, LeaveRequest
from inventory.models import BillOfMaterial, Product, RawMaterial
from production.models import ProductionTask

from .ml import features as F
from .ml import service
from .ml.external import fetch_usd_rwf
from .ml.service import predictor
from .ml.synthetic import generate_records, random_order_payload
from .ml.training import train_models
from .models import APIKey, IncomingOrder, MLModelVersion, PredictionLog, ProductionRecord

TMP_MODEL_DIR = tempfile.mkdtemp(prefix="lm_models_")
TODAY = dt.date.today()


def build_catalogue():
    """Small but complete factory: departments, artisans, materials, products, BOMs, users."""
    cut = Department.objects.create(name="Leather Cutting & Preparation")
    stitch = Department.objects.create(name="Stitching & Assembly")
    finish = Department.objects.create(name="Finishing & Quality Control")
    a1 = Employee.objects.create(first_name="Aline", last_name="Uwase", department=stitch)
    a2 = Employee.objects.create(first_name="Eric", last_name="Mugisha", department=finish)
    a3 = Employee.objects.create(first_name="Grace", last_name="Ineza", department=cut)
    Contract.objects.create(employee=a1, contract_type="Permanent", start_date=TODAY, base_salary=150000)
    Contract.objects.create(employee=a2, contract_type="Intern", start_date=TODAY,
                            end_date=TODAY + dt.timedelta(days=90), base_salary=60000)
    leather = RawMaterial.objects.create(code="PFL-001", name="Full-Grain Leather", unit="Sq Meters",
                                         quantity_in_stock=Decimal("500"), reorder_level=10, unit_cost=1220)
    thread = RawMaterial.objects.create(code="HDN-001", name="Nylon Thread", unit="Spools",
                                        quantity_in_stock=Decimal("900"), reorder_level=100, unit_cost=670)
    clasp = RawMaterial.objects.create(code="MBC-001", name="Magnetic Clasps", unit="Pieces",
                                       quantity_in_stock=Decimal("20"), reorder_level=5, unit_cost=575)
    bag = Product.objects.create(code="Bag-001", name="Laptop Bag", category="Bags", unit_price=16479)
    shoe = Product.objects.create(code="Shoe-001", name="Oxford Shoe", category="Shoes", unit_price=15000)
    belt = Product.objects.create(code="Belt-001", name="Formal Belt", category="Belts", unit_price=9000)
    BillOfMaterial.objects.create(product=bag, material=leather, quantity_per_unit=4)
    BillOfMaterial.objects.create(product=bag, material=thread, quantity_per_unit=3)
    BillOfMaterial.objects.create(product=bag, material=clasp, quantity_per_unit=2)
    BillOfMaterial.objects.create(product=shoe, material=leather, quantity_per_unit=Decimal("4.3"))
    BillOfMaterial.objects.create(product=belt, material=leather, quantity_per_unit=1)
    BillOfMaterial.objects.create(product=belt, material=thread, quantity_per_unit=1)
    admin = User.objects.create_superuser("admin", "admin@example.com", "Admin@2026")
    hr = User.objects.create_user("HR1", password="Web@tech2", is_staff=True)
    viewer = User.objects.create_user("User", password="Web@tech3")
    return {"artisans": (a1, a2, a3), "materials": (leather, thread, clasp), "products": (bag, shoe, belt),
            "admin": admin, "hr": hr, "viewer": viewer}


def client_for(user, **kwargs):
    c = Client(**kwargs)
    c.force_login(user)
    return c


@override_settings(ML_MODEL_DIR=TMP_MODEL_DIR, AI_EXTERNAL_APIS_ENABLED=False)
class AITestCase(TestCase):
    """Base class: catalogue + 400 synthetic records + trained models (once per class)."""

    @classmethod
    def setUpTestData(cls):
        cls.d = build_catalogue()
        cache.clear()
        predictor.clear_cache()
        generate_records(n=400, days_back=365, seed=1)
        cls.summary = train_models(trained_by="tests")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MODEL_DIR, ignore_errors=True)

    def setUp(self):
        cache.clear()
        predictor.clear_cache()


# ---------------------------------------------------------------------------
# Machine learning pipeline
# ---------------------------------------------------------------------------
class MLPipelineTests(AITestCase):
    def test_synthetic_data_is_realistic(self):
        self.assertEqual(ProductionRecord.objects.filter(source="synthetic").count(), 400)
        rec = ProductionRecord.objects.first()
        self.assertGreater(rec.standard_days, 0)
        self.assertEqual(rec.delayed, rec.actual_days > rec.allotted_days)
        rate = ProductionRecord.objects.filter(delayed=True).count() / 400
        self.assertTrue(0.10 < rate < 0.70, f"delay rate {rate} is unrealistic")

    def test_training_reads_api_and_registers_versions(self):
        self.assertEqual(self.summary["source"], "api-inprocess")
        self.assertEqual(self.summary["records"], 400)
        for name in ("delay_classifier", "duration_regressor"):
            active = MLModelVersion.objects.get(name=name, is_active=True)
            self.assertEqual(len(active.candidates), 3)
            self.assertTrue(active.feature_importances)
        clf = MLModelVersion.objects.get(name="delay_classifier", is_active=True)
        reg = MLModelVersion.objects.get(name="duration_regressor", is_active=True)
        self.assertGreater(clf.metrics["roc_auc"], 0.70)
        self.assertGreater(reg.metrics["r2"], 0.50)

    def test_retraining_creates_new_active_version(self):
        train_models(trained_by="tests-2")
        self.assertEqual(MLModelVersion.objects.filter(name="delay_classifier", is_active=True).count(), 1)
        self.assertEqual(MLModelVersion.objects.filter(name="delay_classifier").count(), 2)

    def test_no_target_leakage_in_history_features(self):
        records = [{"id": 1, "artisan_id": 7, "start_date": "2026-01-01", "end_date": "2026-01-05",
                    "delayed": True, "actual_days": 4, "standard_days": 2, "category": "Bags", "quantity": 2}]
        X, y, _, _ = F.build_training_rows(records)
        self.assertEqual(X[0]["artisan_hist_ontime"], F.DEFAULT_HIST_ONTIME)  # own outcome not used

    def test_predict_job_outputs(self):
        bag = self.d["products"][0]
        r = service.predict_job(bag, 3, TODAY + dt.timedelta(days=10))
        self.assertTrue(0 <= r["delay_probability"] <= 1)
        self.assertIn(r["risk_level"], ("Low", "Medium", "High"))
        self.assertGreater(r["predicted_days"], 0)
        probs = [a["delay_probability"] for a in r["artisan_ranking"]]
        self.assertEqual(probs, sorted(probs))
        self.assertEqual(r["recommended_artisan"]["id"], r["artisan_ranking"][0]["id"])
        self.assertTrue(r["recommendations"])

    def test_stock_shortage_is_detected(self):
        bag = self.d["products"][0]  # 2 clasps per unit, only 20 in stock
        r = service.predict_job(bag, 15, TODAY + dt.timedelta(days=30))
        self.assertFalse(r["stock_ok"])
        self.assertEqual(r["shortages"][0]["material_code"], "MBC-001")
        self.assertTrue(any("Restock" in x for x in r["recommendations"]))

    def test_artisan_on_leave_is_excluded_from_ranking(self):
        a1 = self.d["artisans"][0]
        LeaveRequest.objects.create(employee=a1, leave_type="Annual", start_date=TODAY,
                                    end_date=TODAY + dt.timedelta(days=20), status="Approved")
        r = service.predict_job(self.d["products"][2], 5, TODAY + dt.timedelta(days=10))
        self.assertNotIn(a1.pk, [a["id"] for a in r["artisan_ranking"]])

    def test_self_healing_when_model_file_missing(self):
        active = MLModelVersion.objects.get(name="delay_classifier", is_active=True)
        path = Path(TMP_MODEL_DIR) / active.file_name
        backup = path.with_suffix(".bak")
        shutil.copy(path, backup)
        try:
            path.unlink()
            predictor.clear_cache()
            r = service.predict_job(self.d["products"][2], 5, TODAY + dt.timedelta(days=10))
            self.assertIn("v2", r["model_version"])  # retrained automatically
        finally:  # files are not rolled back with the database: restore for the other tests
            shutil.move(backup, path)
            predictor.clear_cache()

    def test_self_healing_when_sklearn_version_differs(self):
        with mock.patch("analytics.ml.service.sklearn.__version__", "0.0-other"):
            predictor.clear_cache()
            status = predictor.status()
        self.assertFalse(status["ready"])
        self.assertIn("scikit-learn", status["reason"])


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
class APITests(AITestCase):
    def setUp(self):
        super().setUp()
        self.staff_key = APIKey.generate(self.d["hr"], "staff")[1]
        self.viewer_key = APIKey.generate(self.d["viewer"], "viewer")[1]
        self.c = Client()
        self.order = {"product_code": "Belt-001", "quantity": 5,
                      "due_date": (TODAY + dt.timedelta(days=12)).isoformat(), "channel": "Online"}

    def post(self, url, data, key):
        return self.c.post(url, json.dumps(data), content_type="application/json", HTTP_X_API_KEY=key)

    def test_public_endpoints(self):
        self.assertEqual(self.c.get("/api/v1/").status_code, 200)
        body = self.c.get("/api/v1/health/").json()
        self.assertEqual(body["data"]["ai_engine"], "ready")

    def test_authentication_required(self):
        self.assertEqual(self.c.get("/api/v1/products/").status_code, 401)
        self.assertEqual(self.c.get("/api/v1/products/", HTTP_X_API_KEY="wrong").status_code, 401)
        self.assertEqual(self.c.get("/api/v1/products/", HTTP_X_API_KEY=self.viewer_key).status_code, 200)
        self.assertEqual(self.c.get("/api/v1/products/", HTTP_AUTHORIZATION=f"Api-Key {self.viewer_key}").status_code, 200)

    def test_revoked_key_is_rejected(self):
        APIKey.objects.filter(user=self.d["viewer"]).update(is_active=False)
        self.assertEqual(self.c.get("/api/v1/tasks/", HTTP_X_API_KEY=self.viewer_key).status_code, 401)

    def test_read_endpoints(self):
        for path in ("products", "materials", "employees", "tasks", "records", "orders", "model",
                     "dashboard/summary", "forecast/materials", "external/fx"):
            r = self.c.get(f"/api/v1/{path}/", HTTP_X_API_KEY=self.viewer_key)
            self.assertEqual(r.status_code, 200, path)
            self.assertEqual(r.json()["status"], "ok", path)

    def test_salaries_are_not_exposed(self):
        body = self.c.get("/api/v1/employees/", HTTP_X_API_KEY=self.viewer_key).content.decode()
        self.assertNotIn("salary", body)

    def test_records_pagination(self):
        r = self.c.get("/api/v1/records/?page=2&page_size=150", HTTP_X_API_KEY=self.viewer_key).json()
        self.assertEqual(r["meta"]["total"], 400)
        self.assertEqual(r["meta"]["pages"], 3)
        self.assertEqual(len(r["data"]), 150)

    def test_staff_can_ingest_order_and_it_is_scored(self):
        r = self.post("/api/v1/orders/", self.order, self.staff_key)
        self.assertEqual(r.status_code, 201)
        pred = r.json()["data"]["prediction"]
        self.assertIn(pred["risk_level"], ("Low", "Medium", "High"))
        self.assertTrue(IncomingOrder.objects.filter(product_code="Belt-001").exists())
        self.assertEqual(PredictionLog.objects.filter(kind="order").count(), 1)

    def test_viewer_cannot_ingest_but_can_predict(self):
        self.assertEqual(self.post("/api/v1/orders/", self.order, self.viewer_key).status_code, 403)
        r = self.post("/api/v1/predict/", self.order, self.viewer_key)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(IncomingOrder.objects.exists())

    def test_order_validation(self):
        r = self.post("/api/v1/orders/", {"product_code": "NOPE", "quantity": 0, "due_date": "2000-01-01"},
                      self.staff_key)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.json()["error"]["details"]), {"product_code", "quantity", "due_date"})
        bad = self.c.post("/api/v1/orders/", "{not json", content_type="application/json",
                          HTTP_X_API_KEY=self.staff_key)
        self.assertEqual(bad.status_code, 400)

    def test_push_record(self):
        rec = {"product_code": "Bag-001", "quantity": 4, "start_date": "2026-09-01",
               "due_date": "2026-09-05", "end_date": "2026-09-07", "defective_units": 1}
        r = self.post("/api/v1/records/", rec, self.staff_key)
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["data"]["delayed"])
        self.assertEqual(ProductionRecord.objects.filter(source="api").count(), 1)

    def test_session_post_requires_csrf(self):
        c = client_for(self.d["hr"], enforce_csrf_checks=True)
        r = c.post("/api/v1/orders/", json.dumps(self.order), content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"]["code"], "csrf_failed")

    def test_method_not_allowed(self):
        self.assertEqual(self.c.delete("/api/v1/tasks/", HTTP_X_API_KEY=self.staff_key).status_code, 405)

    def test_open_api_fallback_when_offline(self):
        with override_settings(AI_EXTERNAL_APIS_ENABLED=True), \
                mock.patch("analytics.ml.external.urllib.request.urlopen", side_effect=OSError("offline")):
            data = fetch_usd_rwf(force=True)
        self.assertEqual(data["status"], "fallback")
        self.assertGreater(data["rate"], 0)

    def test_open_api_live_response_is_parsed(self):
        fake = mock.MagicMock()
        fake.__enter__.return_value.read.return_value = json.dumps(
            {"result": "success", "rates": {"RWF": 1452.5}, "time_last_update_utc": "x"}).encode()
        with override_settings(AI_EXTERNAL_APIS_ENABLED=True), \
                mock.patch("analytics.ml.external.urllib.request.urlopen", return_value=fake):
            data = fetch_usd_rwf(force=True)
        self.assertEqual((data["status"], data["rate"]), ("live", 1452.5))


# ---------------------------------------------------------------------------
# Web pages, workflow and regression of original rules
# ---------------------------------------------------------------------------
class WorkflowTests(AITestCase):
    def make_task(self, **kw):
        defaults = dict(title="Batch", product=self.d["products"][2], target_quantity=5, produced_quantity=0,
                        assigned_to=self.d["artisans"][2], status="Pending",
                        due_date=TODAY + dt.timedelta(days=10))
        defaults.update(kw)
        t = ProductionTask(**defaults)
        t.full_clean()
        t.save()
        return t

    def test_all_pages_render_for_each_role(self):
        task = self.make_task()
        order = service.ingest_order(random_order_payload(), source="test")
        pages = ["/", "/production/tasks/", f"/production/tasks/{task.pk}/", "/production/alerts/",
                 "/inventory/materials/", "/inventory/products/", "/analytics/insights/",
                 f"/analytics/orders/{order.pk}/", "/analytics/predict/", "/analytics/models/",
                 "/analytics/history/", "/analytics/api/"]
        for user in (self.d["admin"], self.d["hr"], self.d["viewer"]):
            c = client_for(user)
            for url in pages:
                self.assertEqual(c.get(url).status_code, 200, f"{user.username} {url}")
        viewer = client_for(self.d["viewer"])
        self.assertEqual(viewer.get(f"/analytics/orders/{order.pk}/convert/").status_code, 302)
        self.assertEqual(viewer.post("/analytics/models/retrain/").status_code, 302)

    def test_dashboard_has_ai_widgets_and_original_widgets(self):
        self.make_task()
        html = client_for(self.d["admin"]).get("/").content.decode()
        for text in ("Total Production Tasks", "Recent Manufacturing Tasks", "Active Workload",
                     "Delay-Risk Monitor", "Live Incoming Orders", "Material Demand Forecast"):
            self.assertIn(text, html)

    def test_whatif_predictor_page(self):
        c = client_for(self.d["viewer"])
        r = c.post("/analytics/predict/", {"product": self.d["products"][0].pk, "quantity": 3,
                                           "due_date": (TODAY + dt.timedelta(days=9)).isoformat(),
                                           "channel": "Internal", "action": "predict"})
        self.assertContains(r, "delay risk")
        self.assertEqual(PredictionLog.objects.filter(kind="whatif").count(), 1)

    def test_convert_order_creates_task_and_deducts_stock(self):
        order = service.ingest_order({"product_code": "Belt-001", "quantity": 10,
                                      "due_date": (TODAY + dt.timedelta(days=15)).isoformat()})
        leather = self.d["materials"][0]
        before = leather.quantity_in_stock
        c = client_for(self.d["hr"])
        r = c.post(f"/analytics/orders/{order.pk}/convert/", {
            "title": "From order", "product": order.product_id, "target_quantity": 10, "produced_quantity": 0,
            "assigned_to": order.assigned_artisan.pk, "status": "Pending",
            "due_date": order.due_date.isoformat(), "description": ""})
        self.assertEqual(r.status_code, 302)
        order.refresh_from_db()
        leather.refresh_from_db()
        self.assertEqual(order.status, "Converted")
        self.assertEqual(leather.quantity_in_stock, before - 10)

    def test_simulate_and_dismiss(self):
        c = client_for(self.d["hr"])
        c.post("/analytics/orders/simulate/", {"count": 3})
        self.assertEqual(IncomingOrder.objects.count(), 3)
        o = IncomingOrder.objects.first()
        c.post(f"/analytics/orders/{o.pk}/dismiss/")
        o.refresh_from_db()
        self.assertEqual(o.status, "Dismissed")

    def test_api_key_management_page(self):
        c = client_for(self.d["hr"])
        c.post("/analytics/api/", {"name": "Terminal"})
        key = APIKey.objects.get(name="Terminal")
        self.assertEqual(len(key.hashed_key), 64)
        c.post(f"/analytics/api/keys/{key.pk}/revoke/")
        key.refresh_from_db()
        self.assertFalse(key.is_active)

    def test_completed_task_feeds_training_data(self):
        task = self.make_task(target_quantity=2)
        task.status, task.produced_quantity = "Completed", 2
        task.full_clean()
        task.save()
        self.assertTrue(ProductionRecord.objects.filter(task=task, source="live").exists())
        task.save()  # saving again must not duplicate
        self.assertEqual(ProductionRecord.objects.filter(task=task).count(), 1)

    def test_task_risk_scoring_states(self):
        task = self.make_task()
        self.assertEqual(service.score_task(task)["state"], "scored")
        ProductionTask.objects.filter(pk=task.pk).update(due_date=TODAY - dt.timedelta(days=2))
        task.refresh_from_db()
        self.assertEqual(service.score_task(task)["state"], "overdue")

    def test_nav_alert_count(self):
        RawMaterial.objects.filter(code="MBC-001").update(quantity_in_stock=1)
        r = client_for(self.d["admin"]).get("/")
        self.assertGreaterEqual(r.context["nav_alerts"]["low_stock"], 1)

    # ---- original business rules still enforced ----
    def test_original_rule_insufficient_stock(self):
        with self.assertRaises(ValidationError):
            self.make_task(product=self.d["products"][0], target_quantity=50)  # clasps: need 100, have 20

    def test_original_rule_stock_deduction_and_refund(self):
        leather = self.d["materials"][0]
        task = self.make_task(target_quantity=5)
        leather.refresh_from_db()
        self.assertEqual(leather.quantity_in_stock, Decimal("495"))
        task.delete()
        leather.refresh_from_db()
        self.assertEqual(leather.quantity_in_stock, Decimal("500"))

    def test_original_rule_new_task_cannot_have_past_due_date(self):
        with self.assertRaises(ValidationError):
            self.make_task(due_date=TODAY - dt.timedelta(days=1))

    def test_original_rule_state_machine(self):
        with self.assertRaises(ValidationError):
            self.make_task(status="Pending", produced_quantity=2)
        with self.assertRaises(ValidationError):
            self.make_task(status="Completed", produced_quantity=1)

    def test_fix_overdue_task_progress_can_be_updated(self):
        task = self.make_task()
        ProductionTask.objects.filter(pk=task.pk).update(due_date=TODAY - dt.timedelta(days=3))
        task = ProductionTask.objects.get(pk=task.pk)
        task.status, task.produced_quantity = "In Progress", 2
        task.full_clean()  # used to raise "The due date cannot be in the past."
        task.save()
        task.due_date = TODAY - dt.timedelta(days=1)  # but moving it to another past date is refused
        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_original_rule_leave_blocks_assignment(self):
        a3 = self.d["artisans"][2]
        LeaveRequest.objects.create(employee=a3, leave_type="Sick", start_date=TODAY,
                                    end_date=TODAY + dt.timedelta(days=5), status="Approved")
        with self.assertRaises(ValidationError):
            self.make_task(assigned_to=a3)

    def test_original_access_control(self):
        viewer = client_for(self.d["viewer"])
        self.assertEqual(viewer.get("/production/tasks/add/").status_code, 302)
        self.assertEqual(viewer.get("/employees/artisans/").status_code, 302)
        self.assertEqual(Client().get("/").status_code, 302)  # login required


class BootstrapTests(TestCase):
    """A fresh installation without any training data initialises itself."""

    @override_settings(ML_MODEL_DIR=tempfile.mkdtemp(prefix="lm_boot_"), AI_EXTERNAL_APIS_ENABLED=False)
    def test_auto_bootstrap_on_first_prediction(self):
        d = build_catalogue()
        cache.clear()
        predictor.clear_cache()
        self.assertFalse(ProductionRecord.objects.exists())
        with mock.patch("analytics.ml.synthetic.generate_records.__defaults__", (600, 540, 42, True, None)):
            r = service.predict_job(d["products"][2], 4, timezone.localdate() + dt.timedelta(days=8))
        self.assertGreater(ProductionRecord.objects.count(), 0)
        self.assertTrue(MLModelVersion.objects.filter(is_active=True).exists())
        self.assertIn(r["risk_level"], ("Low", "Medium", "High"))
