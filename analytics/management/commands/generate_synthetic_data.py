# python manage.py generate_synthetic_data [--records 2000] [--days 540] [--seed 42] [--keep]
from django.core.management.base import BaseCommand, CommandError

from analytics.ml.synthetic import generate_records


class Command(BaseCommand):
    help = "Generate a realistic synthetic production history (training data) from the real catalogue."

    def add_arguments(self, parser):
        parser.add_argument("--records", type=int, default=2000, help="Number of batches (default 2000)")
        parser.add_argument("--days", type=int, default=540, help="History window in days (default 540)")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
        parser.add_argument("--keep", action="store_true", help="Keep existing synthetic records (append)")

    def handle(self, *args, **opts):
        if opts["records"] < 50:
            raise CommandError("Please generate at least 50 records.")
        try:
            n = generate_records(n=opts["records"], days_back=opts["days"], seed=opts["seed"],
                                 clear_existing=not opts["keep"])
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Generated {n} synthetic production records."))
