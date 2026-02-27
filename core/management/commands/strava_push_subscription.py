import os
import requests
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

class Command(BaseCommand):
    help = 'Manage Strava push subscriptions (list, create, delete)'

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, choices=['list', 'create', 'delete'], help='Action to perform: list, create, delete')
        parser.add_argument('subscription_id', nargs='?', type=int, help='ID of the subscription to delete (required for delete)')

    def handle(self, *args, **options):
        action = options['action']
        sub_id = options['subscription_id']

        client_id = getattr(settings, 'STRAVA_CLIENT_ID', os.getenv('STRAVA_CLIENT_ID'))
        client_secret = getattr(settings, 'STRAVA_CLIENT_SECRET', os.getenv('STRAVA_CLIENT_SECRET'))
        verify_token = getattr(settings, 'STRAVA_WEBHOOK_VERIFY_TOKEN', os.getenv('STRAVA_WEBHOOK_VERIFY_TOKEN'))
        callback_url = getattr(settings, 'STRAVA_WEBHOOK_CALLBACK_URL', os.getenv('STRAVA_WEBHOOK_CALLBACK_URL'))

        missing = []
        if not client_id: missing.append('STRAVA_CLIENT_ID')
        if not client_secret: missing.append('STRAVA_CLIENT_SECRET')
        if not verify_token: missing.append('STRAVA_WEBHOOK_VERIFY_TOKEN')
        if not callback_url: missing.append('STRAVA_WEBHOOK_CALLBACK_URL')

        if missing:
            raise CommandError(f"Missing required environment variables/settings: {', '.join(missing)}")

        base_url = "https://www.strava.com/api/v3/push_subscriptions"
        timeout = 20

        try:
            if action == 'list':
                response = requests.get(
                    base_url,
                    params={
                        "client_id": client_id,
                        "client_secret": client_secret
                    },
                    timeout=timeout
                )
                self.stdout.write(f"STATUS: {response.status_code}")
                self.stdout.write(f"BODY: {response.text}")

            elif action == 'create':
                response = requests.post(
                    base_url,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "callback_url": callback_url,
                        "verify_token": verify_token
                    },
                    timeout=timeout
                )
                self.stdout.write(f"STATUS: {response.status_code}")
                self.stdout.write(f"BODY: {response.text}")

            elif action == 'delete':
                if not sub_id:
                    raise CommandError("subscription_id is required for delete action")
                
                url = f"{base_url}/{sub_id}"
                response = requests.delete(
                    url,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret
                    },
                    timeout=timeout
                )
                self.stdout.write(f"STATUS: {response.status_code}")
                self.stdout.write(f"BODY: {response.text}")

        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR("HTTP Request failed. (Details omitted for security)"))
