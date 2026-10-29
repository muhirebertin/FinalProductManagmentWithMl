# python manage.py create_api_key --user admin --name "Simulator"
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from analytics.models import APIKey


class Command(BaseCommand):
    help = "Create an API key for a user. The plain key is printed once."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Username that owns the key")
        parser.add_argument("--name", default="CLI key", help="Label for the key")

    def handle(self, *args, **opts):
        User = get_user_model()
        try:
            user = User.objects.get(username=opts["user"])
        except User.DoesNotExist:
            raise CommandError(f"User '{opts['user']}' does not exist.")
        key, raw = APIKey.generate(user, opts["name"])
        self.stdout.write(self.style.SUCCESS(f"API key '{key.name}' for {user.username} "
                                             f"({'staff' if user.is_staff else 'read-only'}):"))
        self.stdout.write(raw)
        self.stdout.write("Store it safely - it cannot be displayed again.")
