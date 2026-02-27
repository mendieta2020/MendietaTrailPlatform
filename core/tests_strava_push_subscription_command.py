import pytest
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
import requests

@pytest.fixture
def mock_env(settings):
    settings.STRAVA_CLIENT_ID = 'test_id'
    settings.STRAVA_CLIENT_SECRET = 'test_secret'
    settings.STRAVA_WEBHOOK_VERIFY_TOKEN = 'test_token'
    settings.STRAVA_WEBHOOK_CALLBACK_URL = 'http://test.url/webhook'

class MockResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

@pytest.mark.django_db
class TestStravaPushSubscriptionCommand:

    @patch('core.management.commands.strava_push_subscription.requests.get')
    def test_list_subscriptions(self, mock_get, mock_env, capsys):
        mock_get.return_value = MockResponse(200, "[]")
        
        call_command('strava_push_subscription', 'list')
        
        mock_get.assert_called_once_with(
            "https://www.strava.com/api/v3/push_subscriptions",
            params={'client_id': 'test_id', 'client_secret': 'test_secret'},
            timeout=20
        )
        
        captured = capsys.readouterr()
        assert "STATUS: 200" in captured.out
        assert "BODY: []" in captured.out

    @patch('core.management.commands.strava_push_subscription.requests.post')
    def test_create_subscription(self, mock_post, mock_env, capsys):
        mock_post.return_value = MockResponse(201, '{"id": 123}')
        
        call_command('strava_push_subscription', 'create')
        
        mock_post.assert_called_once_with(
            "https://www.strava.com/api/v3/push_subscriptions",
            data={
                "client_id": "test_id",
                "client_secret": "test_secret",
                "callback_url": "http://test.url/webhook",
                "verify_token": "test_token"
            },
            timeout=20
        )
        
        captured = capsys.readouterr()
        assert "STATUS: 201" in captured.out
        assert 'BODY: {"id": 123}' in captured.out

    @patch('core.management.commands.strava_push_subscription.requests.delete')
    def test_delete_subscription(self, mock_delete, mock_env, capsys):
        mock_delete.return_value = MockResponse(204, "")
        
        call_command('strava_push_subscription', 'delete', subscription_id=123)
        
        mock_delete.assert_called_once_with(
            "https://www.strava.com/api/v3/push_subscriptions/123",
            data={'client_id': 'test_id', 'client_secret': 'test_secret'},
            timeout=20
        )
        
        captured = capsys.readouterr()
        assert "STATUS: 204" in captured.out

    def test_missing_env_vars(self, settings):
        settings.STRAVA_CLIENT_ID = None
        
        with pytest.raises(CommandError) as exc:
            call_command('strava_push_subscription', 'list')
            
        assert "Missing required environment variables/settings: STRAVA_CLIENT_ID" in str(exc.value)

    @patch('core.management.commands.strava_push_subscription.requests.get')
    def test_request_exception(self, mock_get, mock_env, capsys):
        mock_get.side_effect = requests.exceptions.RequestException("Timeout or something")
        
        call_command('strava_push_subscription', 'list')
        
        captured = capsys.readouterr()
        assert "HTTP Request failed. (Details omitted for security)" in captured.out
