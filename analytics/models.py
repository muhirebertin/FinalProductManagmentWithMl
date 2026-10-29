# analytics/models.py
"""
Data models for the AI & Analytics extension.

None of these models modify the existing tables of the `employees`,
`inventory` or `production` apps. They only *reference* them, and every
reference uses on_delete=SET_NULL so that deleting a product, artisan or
task never fails because of analytics data.
"""
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from employees.models import Employee
from inventory.models import Product
from production.models import ProductionTask


# ---------------------------------------------------------------------------
# 1. TRAINING DATA: historical production batches
# ---------------------------------------------------------------------------
class ProductionRecord(models.Model):
    """
    One finished production batch. This is the training dataset of the
    machine-learning models. Each row keeps a *snapshot* of the facts that were
    known when the batch started (so later edits to products/artisans do not
    rewrite history) plus the observed outcome (actual duration, delay, defects).
    """
    SOURCE_CHOICES = [
        ("synthetic", "Synthetic (generated)"),
        ("api", "External API push"),
        ("live", "Completed production task"),
    ]

    # --- references (optional; history survives deletions) ---
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="production_records")
    artisan = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="production_records")
    task = models.OneToOneField(ProductionTask, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="production_record")

    # --- snapshot of the job (inputs known at start) ---
    product_code = models.CharField(max_length=20)
    product_name = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    material_cost_per_unit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bom_items = models.PositiveIntegerField(default=0)
    bom_qty_per_unit = models.FloatField(default=0)
    standard_days = models.FloatField(help_text="Engineering standard duration (days) for the batch")
    allotted_days = models.PositiveIntegerField(help_text="Days the manager allowed (due date - start date)")
    artisan_name = models.CharField(max_length=101, blank=True)
    artisan_contract = models.CharField(max_length=20, default="None")
    artisan_department = models.CharField(max_length=100, blank=True)
    dept_match = models.BooleanField(default=False)
    artisan_workload = models.PositiveIntegerField(default=0, help_text="Other active tasks at start")
    stock_coverage = models.FloatField(default=5.0, help_text="Min(stock / requirement) over the BOM, capped at 5")

    # --- dates & outcome ---
    start_date = models.DateField()
    due_date = models.DateField()
    end_date = models.DateField()
    actual_days = models.FloatField()
    delayed = models.BooleanField()
    defective_units = models.PositiveIntegerField(default=0)

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="synthetic")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        indexes = [
            models.Index(fields=["start_date"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        return f"{self.product_code} x{self.quantity} ({self.start_date})"

    @property
    def delay_days(self):
        return round(self.actual_days - self.allotted_days, 1)

    @property
    def defect_rate(self):
        return round(100.0 * self.defective_units / self.quantity, 1) if self.quantity else 0.0


# ---------------------------------------------------------------------------
# 2. NEW INCOMING DATA: orders that arrive through the API / simulator / UI
# ---------------------------------------------------------------------------
class IncomingOrder(models.Model):
    """
    A new production request that arrives in real time (sales channel,
    storefront, corporate client...). As soon as it is received the AI engine
    scores it and stores the prediction on the same row.
    """
    STATUS_CHOICES = [
        ("New", "New"),
        ("Converted", "Converted to task"),
        ("Dismissed", "Dismissed"),
    ]
    RISK_CHOICES = [("Low", "Low"), ("Medium", "Medium"), ("High", "High")]
    CHANNEL_CHOICES = [
        ("Storefront", "Storefront"),
        ("Corporate", "Corporate"),
        ("Online", "Online"),
        ("Export", "Export"),
        ("Internal", "Internal"),
    ]

    reference = models.CharField(max_length=30, unique=True)
    customer = models.CharField(max_length=120, blank=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="Storefront")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, related_name="incoming_orders")
    product_code = models.CharField(max_length=20)
    quantity = models.PositiveIntegerField()
    due_date = models.DateField()
    requested_artisan = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name="requested_orders")
    received_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=30, default="api", help_text="api / simulator / web")

    # --- AI prediction (filled automatically on arrival) ---
    delay_probability = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES, blank=True)
    predicted_days = models.FloatField(null=True, blank=True)
    predicted_completion = models.DateField(null=True, blank=True)
    recommended_artisan = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name="recommended_orders")
    stock_ok = models.BooleanField(default=True)
    prediction = models.JSONField(default=dict, blank=True, help_text="Full prediction payload")
    model_version = models.CharField(max_length=40, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="New")
    converted_task = models.ForeignKey(ProductionTask, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="source_orders")

    class Meta:
        ordering = ["-received_at", "-id"]

    def __str__(self):
        return f"{self.reference} - {self.product_code} x{self.quantity}"

    @property
    def delay_percent(self):
        return int(round((self.delay_probability or 0) * 100))

    @property
    def assigned_artisan(self):
        return self.requested_artisan or self.recommended_artisan


# ---------------------------------------------------------------------------
# 3. AUDIT TRAIL of every prediction served
# ---------------------------------------------------------------------------
class PredictionLog(models.Model):
    KIND_CHOICES = [
        ("order", "Incoming order"),
        ("task", "Production task"),
        ("whatif", "What-if simulation"),
        ("api", "API /predict call"),
    ]
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    object_ref = models.CharField(max_length=60, blank=True)
    inputs = models.JSONField(default=dict)
    outputs = models.JSONField(default=dict)
    model_version = models.CharField(max_length=40, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} {self.object_ref} @ {self.created_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# 4. MODEL REGISTRY (versioned trained models)
# ---------------------------------------------------------------------------
class MLModelVersion(models.Model):
    NAME_CHOICES = [
        ("delay_classifier", "Delay-risk classifier"),
        ("duration_regressor", "Duration regressor"),
    ]
    name = models.CharField(max_length=40, choices=NAME_CHOICES)
    version = models.PositiveIntegerField()
    algorithm = models.CharField(max_length=80)
    file_name = models.CharField(max_length=200)
    metrics = models.JSONField(default=dict)
    candidates = models.JSONField(default=list, help_text="Scores of every algorithm compared")
    feature_importances = models.JSONField(default=list)
    n_train = models.PositiveIntegerField(default=0)
    n_test = models.PositiveIntegerField(default=0)
    data_source = models.CharField(max_length=60, blank=True)
    sklearn_version = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    trained_by = models.CharField(max_length=150, blank=True)
    trained_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-trained_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["name", "version"], name="unique_model_name_version")
        ]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.algorithm})"

    @property
    def label(self):
        return f"{self.name}-v{self.version}"


# ---------------------------------------------------------------------------
# 5. API KEYS for machine clients (simulators, MES terminals, scripts)
# ---------------------------------------------------------------------------
class APIKey(models.Model):
    """
    API keys are stored hashed (SHA-256). The plain key is shown only once,
    when it is created. A key acts with the permissions of its owner.
    """
    name = models.CharField(max_length=80)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys")
    prefix = models.CharField(max_length=12, db_index=True)
    hashed_key = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "API key"

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @staticmethod
    def hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def generate(cls, user, name="Default key"):
        """Create a key and return (instance, plain_text_key)."""
        raw = "lm_" + secrets.token_urlsafe(32)
        obj = cls.objects.create(name=name, user=user, prefix=raw[:10], hashed_key=cls.hash(raw))
        return obj, raw

    @classmethod
    def authenticate(cls, raw_key: str):
        if not raw_key:
            return None
        try:
            key = cls.objects.select_related("user").get(hashed_key=cls.hash(raw_key.strip()), is_active=True)
        except cls.DoesNotExist:
            return None
        if not key.user.is_active:
            return None
        cls.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return key


# ---------------------------------------------------------------------------
# 6. LAST GOOD VALUE of external (Open API) data
# ---------------------------------------------------------------------------
class ExternalDataSnapshot(models.Model):
    key = models.CharField(max_length=60, unique=True)
    payload = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.key} @ {self.fetched_at:%Y-%m-%d %H:%M}"
