import logging
from unittest.mock import patch
import pytest

from core.utils.logging import sanitize_secrets

class TestLoggingSanitizer:
    def test_sanitizer_redacts_known_secret_keys(self):
        payload = {
            "client_secret": "my-secret-123",
            "refresh_token": "refresh-123",
            "access_token": "access-123",
            "authorization": "Bearer xyz",
            "code": "code-123",
            "token": "token-123",
            "password": "pwd-123",
            "safe_key": "safe_value",
            "nested": {
                "client_secret": "nested-secret"
            },
            "array": [
                {"refresh_token": "array-refresh"}
            ]
        }
        
        sanitized = sanitize_secrets(payload)
        
        assert sanitized["client_secret"] == "REDACTED"
        assert sanitized["refresh_token"] == "REDACTED"
        assert sanitized["access_token"] == "REDACTED"
        assert sanitized["authorization"] == "REDACTED"
        assert sanitized["code"] == "REDACTED"
        assert sanitized["token"] == "REDACTED"
        assert sanitized["password"] == "REDACTED"
        assert sanitized["safe_key"] == "safe_value"
        assert sanitized["nested"]["client_secret"] == "REDACTED"
        assert sanitized["array"][0]["refresh_token"] == "REDACTED"
        
        # Ensure values don't contain secret substrings
        assert "my-secret-123" not in str(sanitized)
        assert "refresh-123" not in str(sanitized)

    def test_simulated_log_call_does_not_include_secret_substrings(self, caplog):
        logger = logging.getLogger("test.logger")
        logger.setLevel(logging.INFO)
        
        secret = "super-secret-123456"
        payload = {
            "client_secret": secret,
            "status": "ok"
        }
        
        # Simulate the celery failure handler kwargs or a direct payload log
        sanitized = sanitize_secrets(payload)
        logger.info("Test log", extra={"task_kwargs": sanitized})
        
        # Check that the secret is completely absent from the log records
        for record in caplog.records:
            assert secret not in str(record.__dict__)
            assert secret not in record.message
