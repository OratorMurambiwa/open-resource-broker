"""Azure and GCP init inquiries must work before provider instances exist."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import HTTPError

import orb.interface.init_command_handler as init_handler
from orb.providers.azure.configuration.config import AzureProviderConfig
from orb.providers.azure.strategy.azure_provider_strategy import AzureProviderStrategy
from orb.providers.gcp.configuration.config import GCPProviderConfig
from orb.providers.gcp.services.health_check_service import GCPHealthCheckService
from orb.providers.gcp.strategy.gcp_provider_strategy import GCPProviderStrategy


@pytest.fixture(params=[("azure", AzureProviderStrategy), ("gcp", GCPProviderStrategy)])
def init_container(request):
    provider_type, strategy = request.param
    registration = MagicMock(strategy_class=strategy)
    registry = MagicMock()
    registry._get_type_registration.return_value = registration
    container = MagicMock()
    container.get.return_value = registry
    return provider_type, strategy, container


def test_init_credentials_work_from_strategy_class(init_container, monkeypatch) -> None:
    provider_type, strategy, container = init_container
    if strategy is AzureProviderStrategy:
        token_provider = MagicMock()
        monkeypatch.setattr(
            "orb.providers.azure.services.health_check_service.DefaultAzureAccessTokenProvider",
            token_provider,
        )
    else:
        authenticate = MagicMock(return_value="example-project")
        monkeypatch.setattr(GCPHealthCheckService, "authenticate", authenticate)

    sources = init_handler._get_available_credential_sources(provider_type, container)
    assert sources and all("config_delta" in source for source in sources)
    requirements = init_handler._get_credential_requirements(provider_type, container)
    if provider_type == "azure":
        assert requirements["client_id"]["prompt"] is True
    else:
        assert requirements == {}
    assert init_handler._get_operational_requirements(provider_type, container)
    success, error = init_handler._test_provider_credentials(
        provider_type, sources[0]["name"], container=container
    )

    assert success is True
    assert error == ""


def test_gcp_init_reports_authentication_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        GCPHealthCheckService,
        "authenticate",
        MagicMock(side_effect=RuntimeError("ADC unavailable")),
    )

    result = GCPProviderStrategy.test_credentials("adc")

    assert result == {"success": False, "error": "GCP credential check failed: ADC unavailable"}


def test_azure_init_uses_selected_managed_identity(monkeypatch) -> None:
    token_provider = MagicMock()
    monkeypatch.setattr(
        "orb.providers.azure.services.health_check_service.DefaultAzureAccessTokenProvider",
        token_provider,
    )

    result = AzureProviderStrategy.test_credentials(client_id="managed-identity-id")

    assert result == {"success": True}
    assert token_provider.call_args.kwargs["client_id"] == "managed-identity-id"


def test_interactive_init_collects_azure_and_gcp_config(init_container, monkeypatch) -> None:
    provider_type, strategy, container = init_container
    monkeypatch.setattr(strategy, "get_contextual_operational_param_choices", lambda *_args: [])
    if provider_type == "gcp":
        monkeypatch.setattr(strategy, "get_operational_param_default", lambda *_args: "")
    monkeypatch.setattr(
        init_handler,
        "_get_available_schedulers",
        lambda: [{"type": "default", "display_name": "Default", "description": "Default"}],
    )
    monkeypatch.setattr(
        init_handler,
        "_get_available_providers",
        lambda _container: [
            {"type": provider_type, "display_name": provider_type, "description": provider_type}
        ],
    )
    monkeypatch.setattr(strategy, "test_credentials", lambda *_args, **_kwargs: {"success": True})
    values = (
        ["", "", "", "", "subscription-id", "resource-group", "eastus2", "n", "n"]
        if provider_type == "azure"
        else ["", "", "", "example-project", "us-central1", "n", "n"]
    )
    answers = iter(values)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    result = init_handler._interactive_setup(container)

    config = result["providers"][0]["config"]
    if provider_type == "azure":
        assert config == {
            "subscription_id": "subscription-id",
            "resource_group": "resource-group",
            "region": "eastus2",
        }
    else:
        assert config == {"project_id": "example-project", "region": "us-central1"}


def test_azure_discovery_uses_selected_subscription(monkeypatch) -> None:
    from orb.providers.azure.services import init_discovery

    subscriptions = MagicMock(return_value=[("sub-a", "Subscription A")])
    groups = MagicMock(return_value=[("workers", "workers")])
    locations = MagicMock(return_value=[("uksouth", "UK South")])
    monkeypatch.setattr(init_discovery, "list_subscriptions", subscriptions)
    monkeypatch.setattr(init_discovery, "list_resource_groups", groups)
    monkeypatch.setattr(init_discovery, "list_locations", locations)

    selected = {"client_id": "identity-id"}
    assert AzureProviderStrategy.get_contextual_operational_param_choices(
        "subscription_id", selected
    ) == [("sub-a", "Subscription A")]
    selected["subscription_id"] = "sub-a"
    assert AzureProviderStrategy.get_contextual_operational_param_choices(
        "resource_group", selected
    ) == [("workers", "workers")]
    assert AzureProviderStrategy.get_contextual_operational_param_choices("region", selected) == [
        ("uksouth", "UK South")
    ]
    subscriptions.assert_called_once_with("identity-id")
    groups.assert_called_once_with("identity-id", "sub-a")
    locations.assert_called_once_with("identity-id", "sub-a")


def test_gcp_discovery_uses_selected_project(monkeypatch) -> None:
    from orb.providers.gcp.services import init_discovery

    monkeypatch.setattr(
        init_discovery,
        "list_projects",
        lambda: [("another-project", "Another"), ("default-project", "Default")],
    )
    monkeypatch.setattr(init_discovery, "default_project", lambda: "default-project")
    regions = MagicMock(return_value=[("europe-west2", "europe-west2")])
    monkeypatch.setattr(init_discovery, "list_regions", regions)

    choices = GCPProviderStrategy.get_contextual_operational_param_choices("project_id", {})
    assert choices[1][0] == "default-project"
    assert GCPProviderStrategy.get_operational_param_default("project_id") == "default-project"
    assert GCPProviderStrategy.get_contextual_operational_param_choices(
        "region", {"project_id": "default-project"}
    ) == [("europe-west2", "europe-west2")]
    regions.assert_called_once_with("default-project")


def test_gcp_region_discovery_uses_marked_fallback_on_forbidden(monkeypatch) -> None:
    from orb.providers.gcp.services import init_discovery

    response = MagicMock(status_code=403)
    error = HTTPError("Forbidden", response=response)
    monkeypatch.setattr(init_discovery, "list_regions", MagicMock(side_effect=error))

    choices = GCPProviderStrategy.get_contextual_operational_param_choices(
        "region", {"project_id": "example-project"}
    )

    assert ("us-central1", "Iowa (unverified)") in choices
    assert GCPProviderStrategy.get_operational_param_default("region") == "us-central1"


def test_gcp_init_keeps_selected_project_when_region_listing_fails(monkeypatch) -> None:
    from orb.providers.gcp.services import init_discovery

    monkeypatch.setattr(
        init_discovery,
        "list_projects",
        lambda: [("first-project", "First"), ("default-project", "Default")],
    )
    monkeypatch.setattr(init_discovery, "default_project", lambda: "default-project")
    regions = MagicMock(side_effect=RuntimeError("Compute API unavailable"))
    monkeypatch.setattr(init_discovery, "list_regions", regions)
    container = MagicMock()
    answers = iter(["", "europe-west2"])
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", answer)
    selected = init_handler._prompt_operational_params(
        GCPProviderStrategy, container=container, provider_config={"type": "gcp"}
    )

    assert selected == {"project_id": "default-project", "region": "europe-west2"}
    assert prompts[0] == "  Select (2): "
    regions.assert_called_once_with("default-project")
    container.get.return_value.info.assert_any_call(
        "  Could not discover Default GCP region: Compute API unavailable"
    )


def test_interactive_init_selects_discovered_resources(init_container, monkeypatch) -> None:
    provider_type, strategy, container = init_container
    monkeypatch.setattr(
        init_handler,
        "_get_available_schedulers",
        lambda: [{"type": "default", "display_name": "Default", "description": "Default"}],
    )
    monkeypatch.setattr(
        init_handler,
        "_get_available_providers",
        lambda _container: [
            {"type": provider_type, "display_name": provider_type, "description": provider_type}
        ],
    )
    monkeypatch.setattr(strategy, "test_credentials", lambda *_args, **_kwargs: {"success": True})

    if provider_type == "azure":
        from orb.providers.azure.services import init_discovery

        monkeypatch.setattr(init_discovery, "list_subscriptions", lambda _client: [("sub-a", "A")])
        monkeypatch.setattr(
            init_discovery,
            "list_resource_groups",
            lambda _client, subscription: [("workers", subscription)],
        )
        monkeypatch.setattr(
            init_discovery,
            "list_locations",
            lambda _client, _subscription: [("uksouth", "UK South")],
        )
        answers = iter(["", "", "", "", "", "", "", "n", "n"])
        expected = {"subscription_id": "sub-a", "resource_group": "workers", "region": "uksouth"}
    else:
        from orb.providers.gcp.services import init_discovery

        monkeypatch.setattr(
            init_discovery,
            "list_projects",
            lambda: [("another-project", "Another"), ("default-project", "Default")],
        )
        monkeypatch.setattr(init_discovery, "default_project", lambda: "default-project")
        monkeypatch.setattr(
            init_discovery, "list_regions", lambda _project: [("europe-west2", "London")]
        )
        answers = iter(["", "", "", "", "", "n", "n"])
        expected = {"project_id": "default-project", "region": "europe-west2"}

    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    result = init_handler._interactive_setup(container)

    assert result["providers"][0]["config"] == expected


def test_additional_azure_provider_uses_selected_identity_and_subscription(monkeypatch) -> None:
    from orb.providers.azure.services import init_discovery

    registration = MagicMock(strategy_class=AzureProviderStrategy)
    registry = MagicMock()
    registry._get_type_registration.return_value = registration
    container = MagicMock()
    container.get.return_value = registry
    monkeypatch.setattr(
        init_handler,
        "_get_available_providers",
        lambda _container: [{"type": "azure", "display_name": "Azure", "description": "Azure"}],
    )
    monkeypatch.setattr(
        AzureProviderStrategy, "test_credentials", lambda *_args, **_kwargs: {"success": True}
    )
    subscriptions = MagicMock(return_value=[("sub-a", "Subscription A")])
    groups = MagicMock(return_value=[("workers", "workers")])
    locations = MagicMock(return_value=[("uksouth", "UK South")])
    monkeypatch.setattr(init_discovery, "list_subscriptions", subscriptions)
    monkeypatch.setattr(init_discovery, "list_resource_groups", groups)
    monkeypatch.setattr(init_discovery, "list_locations", locations)
    answers = iter(["", "managed-id", "", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    result = init_handler._configure_additional_provider(container)

    assert result == {
        "type": "azure",
        "config": {
            "client_id": "managed-id",
            "subscription_id": "sub-a",
            "resource_group": "workers",
            "region": "uksouth",
        },
        "infrastructure_defaults": {},
    }
    subscriptions.assert_called_once_with("managed-id")
    groups.assert_called_once_with("managed-id", "sub-a")
    locations.assert_called_once_with("managed-id", "sub-a")


@pytest.mark.parametrize(
    ("provider_type", "config_model", "config_values"),
    [
        ("azure", AzureProviderConfig, {"subscription_id": "00000000-0000-0000-0000-000000000001"}),
        ("gcp", GCPProviderConfig, {"project_id": "example-project"}),
    ],
)
def test_discovery_passes_only_provider_config_to_strict_models(
    provider_type, config_model, config_values
) -> None:
    registry = MagicMock()
    strategy = MagicMock()
    strategy.discover_infrastructure_interactive.return_value = {}

    def create_strategy(_provider_type, config):
        config_model.model_validate(config)
        return strategy

    registry.create_strategy_by_type.side_effect = create_strategy
    container = MagicMock()

    result = init_handler._discover_infrastructure(
        provider_type, {"type": provider_type, **config_values}, registry, container
    )

    assert result == {}
    registry.create_strategy_by_type.assert_called_once_with(provider_type, config_values)
    strategy.discover_infrastructure_interactive.assert_called_once_with(
        {"type": provider_type, "config": config_values}
    )
