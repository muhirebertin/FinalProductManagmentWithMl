# python manage.py train_models [--api-url http://127.0.0.1:8000 --api-key lm_xxx]
import json

from django.core.management.base import BaseCommand, CommandError

from analytics.ml.training import TrainingError, train_models


class Command(BaseCommand):
    help = ("Read the training data from the REST API, train and compare the models, "
            "and deploy the best ones (new versions in the model registry).")

    def add_arguments(self, parser):
        parser.add_argument("--api-url", default=None,
                            help="Read data over HTTP from a running server, e.g. http://127.0.0.1:8000. "
                                 "If omitted, the API is called in-process.")
        parser.add_argument("--api-key", default=None, help="API key used with --api-url")

    def handle(self, *args, **opts):
        if opts["api_url"] and not opts["api_key"]:
            raise CommandError("--api-key is required with --api-url (create one with create_api_key).")
        self.stdout.write("Reading training data from the API ...")
        try:
            s = train_models(api_url=opts["api_url"], api_key=opts["api_key"], trained_by="manage.py train_models")
        except TrainingError as exc:
            raise CommandError(str(exc))
        self.stdout.write(f"Records: {s['records']} (train {s['n_train']} / test {s['n_test']}, "
                          f"time split at {s['split_date']}) - source: {s['source']}")
        for name in ("delay_classifier", "duration_regressor"):
            m = s[name]
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{name}  ->  v{m['version']}  [{m['algorithm']}]"))
            for c in m["candidates"]:
                self.stdout.write("   " + json.dumps(c))
            shown = {k: v for k, v in m["metrics"].items() if k != "confusion_matrix"}
            self.stdout.write("   selected metrics: " + json.dumps(shown))
        self.stdout.write(self.style.SUCCESS(f"\nTraining completed in {s['seconds']} s. Models deployed."))
