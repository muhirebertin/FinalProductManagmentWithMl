# python manage.py simulate_orders --count 10 --interval 3 [--api-url http://127.0.0.1:8000 --api-key lm_xxx]
import json
import random
import time
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from analytics.ml.service import ModelUnavailable, OrderValidationError, ingest_order
from analytics.ml.synthetic import random_order_payload


class Command(BaseCommand):
    help = ("Simulate a stream of new incoming orders. Each order is POSTed to /api/v1/orders/ "
            "(over HTTP when --api-url is given) and scored by the AI engine in real time.")

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10, help="Number of orders (0 = run until Ctrl+C)")
        parser.add_argument("--interval", type=float, default=3.0, help="Seconds between orders")
        parser.add_argument("--api-url", default=None, help="e.g. http://127.0.0.1:8000")
        parser.add_argument("--api-key", default=None, help="Staff API key (required with --api-url)")
        parser.add_argument("--seed", type=int, default=None)

    def _post_http(self, url, key, payload):
        req = urllib.request.Request(
            url.rstrip("/") + "/api/v1/orders/", data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "X-API-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))["data"]
        except urllib.error.HTTPError as exc:
            raise CommandError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
        except urllib.error.URLError as exc:
            raise CommandError(f"Cannot reach {url}: {exc.reason}. Is 'python manage.py runserver' running?")

    def handle(self, *args, **o):
        if o["api_url"] and not o["api_key"]:
            raise CommandError("--api-key is required with --api-url.")
        rnd = random.Random(o["seed"])
        mode = f"HTTP -> {o['api_url']}" if o["api_url"] else "in-process"
        self.stdout.write(f"Streaming incoming orders ({mode}). Press Ctrl+C to stop.")
        i = 0
        try:
            while o["count"] == 0 or i < o["count"]:
                payload = random_order_payload(rnd)
                if o["api_url"]:
                    d = self._post_http(o["api_url"], o["api_key"], payload)
                    ref, p = d["reference"], d["prediction"]
                    line = (f"{ref}  {d['product_code']:<9} x{d['quantity']:<3} due {d['due_date']}  ->  "
                            f"{p['risk_level']:<6} risk {round(p['delay_probability'] * 100):>3}%  "
                            f"~{p['predicted_days']} days  artisan: {p['recommended_artisan']}")
                else:
                    try:
                        order = ingest_order(payload, source="simulator")
                    except (OrderValidationError, ModelUnavailable) as exc:
                        raise CommandError(str(exc))
                    line = (f"{order.reference}  {order.product_code:<9} x{order.quantity:<3} due {order.due_date}  ->  "
                            f"{order.risk_level:<6} risk {order.delay_percent:>3}%  ~{order.predicted_days} days  "
                            f"artisan: {order.recommended_artisan}")
                style = self.style.ERROR if " High " in line else (
                    self.style.WARNING if "Medium" in line else self.style.SUCCESS)
                self.stdout.write(style(line))
                i += 1
                if o["count"] == 0 or i < o["count"]:
                    time.sleep(max(0.0, o["interval"]))
        except KeyboardInterrupt:
            self.stdout.write("\nStopped.")
        self.stdout.write(self.style.SUCCESS(f"{i} order(s) sent."))
