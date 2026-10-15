"""GCP init validates Application Default Credentials before provider construction."""

from unittest.mock import MagicMock

import google.auth

from orb.providers.gcp.services.health_check_service import GCPHealthCheckService


def test_authentication_refreshes_adc(monkeypatch) -> None:
    credentials = MagicMock()
    auth_default = MagicMock(return_value=(credentials, "selected-project"))
    monkeypatch.setattr(google.auth, "default", auth_default)

    assert GCPHealthCheckService.authenticate() == "selected-project"
    credentials.refresh.assert_called_once()
