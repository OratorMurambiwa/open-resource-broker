"""GCP init validates Application Default Credentials before provider construction."""

import base64
import json
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import google.auth
import google.auth.transport.requests
from google.oauth2 import service_account

from orb.providers.gcp.services.health_check_service import GCPHealthCheckService


def test_authentication_refreshes_adc(monkeypatch) -> None:
    credentials = MagicMock()
    auth_default = MagicMock(return_value=(credentials, "selected-project"))
    monkeypatch.setattr(google.auth, "default", auth_default)

    assert GCPHealthCheckService.authenticate() == "selected-project"
    auth_default.assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh.assert_called_once()


def test_service_account_adc_refresh_includes_cloud_platform_scope(monkeypatch) -> None:
    signer = MagicMock()
    signer.key_id = "test-key"
    signer.sign.return_value = b"test-signature"
    request_payloads = []

    def default_credentials(*, scopes):
        credentials = service_account.Credentials(
            signer=signer,
            service_account_email="test@example.iam.gserviceaccount.com",
            token_uri="https://oauth2.googleapis.com/token",
            scopes=scopes,
        )
        return credentials, "test-project"

    def token_request(**kwargs):
        request_payloads.append(kwargs["body"])
        return MagicMock(
            status=200,
            data=json.dumps(
                {"access_token": "test-token", "expires_in": 3600, "token_type": "Bearer"}
            ).encode(),
        )

    monkeypatch.setattr(google.auth, "default", default_credentials)
    monkeypatch.setattr(google.auth.transport.requests, "Request", lambda: token_request)

    assert GCPHealthCheckService.authenticate() == "test-project"
    assertion = parse_qs(request_payloads[0].decode())["assertion"][0]
    encoded_claims = assertion.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(encoded_claims + "=="))
    assert claims["scope"] == "https://www.googleapis.com/auth/cloud-platform"
