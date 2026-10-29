# python manage.py setup_ai [--force] [--orders 8]
import random

from django.core.management import call_command
from django.core.management.base import BaseCommand

from analytics.ml.service import ingest_order
from analytics.ml.synthetic import random_order_payload
from analytics.models import ProductionRecord
from analytics.signals import record_from_task
from production.models import ProductionTask


class Command(BaseCommand):
    help = "One-shot setup of the AI module: training data + model training + demo incoming orders."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Regenerate the synthetic history")
        parser.add_argument("--orders", type=int, default=8, help="Demo incoming orders to create (default 8)")

    def handle(self, *args, **o):
        self.stdout.write(self.style.MIGRATE_HEADING("1/4 Training data"))
        if o["force"] or ProductionRecord.objects.filter(source="synthetic").count() < 200:
            call_command("generate_synthetic_data", stdout=self.stdout)
        else:
            self.stdout.write("   Synthetic history already present (use --force to regenerate).")

        self.stdout.write(self.style.MIGRATE_HEADING("2/4 Importing completed real tasks"))
        n = sum(1 for t in ProductionTask.objects.filter(status="Completed") if record_from_task(t))
        self.stdout.write(f"   {n} completed task(s) added to the history.")

        self.stdout.write(self.style.MIGRATE_HEADING("3/4 Training models (data read through the API)"))
        call_command("train_models", stdout=self.stdout)

        self.stdout.write(self.style.MIGRATE_HEADING("4/4 Demo incoming orders"))
        rnd = random.Random(7)
        for _ in range(max(0, o["orders"])):
            order = ingest_order(random_order_payload(rnd), source="simulator")
            self.stdout.write(f"   {order.reference}: {order.product_code} x{order.quantity} -> "
                              f"{order.risk_level} ({order.delay_percent}%)")
        self.stdout.write(self.style.SUCCESS("\nAI module ready. Start the server: python manage.py runserver"))
