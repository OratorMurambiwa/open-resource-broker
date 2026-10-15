"""GCP provider health checks and operational metadata."""

from __future__ import annotations

import time
from typing import Optional

from orb.domain.base.ports import LoggingPort
from orb.infrastructure.mocking.dry_run_context import is_dry_run_active
from orb.providers.base.strategy import ProviderHealthStatus
from orb.providers.gcp.configuration.config import GCPProviderConfig


class GCPHealthCheckService:
    """Own GCP provider health checks and credential helpers."""

    def __init__(self, config: GCPProviderConfig, logger: LoggingPort) -> None:
        self._config = config
        self._logger = logger

    def check_health(self) -> ProviderHealthStatus:
        """Verify GCP credentials by refreshing the ADC token."""
        start_time = time.time()
        if is_dry_run_active():
            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.healthy(
                f"GCP provider healthy (DRY-RUN) - Project: {self._config.project_id}",
                response_time_ms,
            )

        try:
            project = self.authenticate()

            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.healthy(
                f"GCP provider healthy - Project: {project or self._config.project_id}",
                response_time_ms,
            )
        except Exception as exc:
            self._logger.warning("GCP health check failed: %s", exc, exc_info=True)
            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.unhealthy(
                f"GCP credential check failed: {exc!s}",
                {
                    "error": str(exc),
                    "project_id": self._config.project_id,
                    "response_time_ms": response_time_ms,
                    "hint": (
                        "Set GOOGLE_APPLICATION_CREDENTIALS or run under workload identity / gcloud ADC "
                        "(https://cloud.google.com/docs/authentication/application-default-credentials)"
                    ),
                },
            )

    @staticmethod
    def authenticate() -> str | None:
        """Refresh Application Default Credentials and return their project."""
        import google.auth
        import google.auth.transport.requests

        credentials, project = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
        return project

    @classmethod
    def get_available_credential_sources(cls) -> list[dict]:
        """Return supported credential sources."""
        return [
            {
                "name": "adc",
                "description": "Application Default Credentials / workload identity",
                "config_delta": {},
            }
        ]

    @classmethod
    def test_credentials(cls, credential_source: Optional[str] = None, **kwargs) -> dict:
        """Test ADC availability without fetching real SDK clients."""
        del credential_source, kwargs
        if is_dry_run_active():
            return {"success": True}
        try:
            return {"success": True, "project_id": cls.authenticate()}
        except Exception as exc:
            return {"success": False, "error": f"GCP credential check failed: {exc!s}"}

    @classmethod
    def get_credential_requirements(cls) -> dict:
        """Describe GCP auth requirements."""
        return {}

    @classmethod
    def get_operational_requirements(cls) -> dict:
        """Describe non-secret operational requirements."""
        return {
            "project_id": {"required": True, "description": "GCP project ID"},
            "region": {"required": True, "description": "Default GCP region"},
        }
