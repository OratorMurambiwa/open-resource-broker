"""Azure init discovery uses the selected identity and subscription."""

from unittest.mock import MagicMock

from orb.providers.azure.services import init_discovery


def test_subscription_discovery_closes_sdk_resources(monkeypatch) -> None:
    credential = MagicMock()
    client = MagicMock()
    client.subscriptions.list.return_value = [
        MagicMock(subscription_id="sub-a", display_name="Zebra"),
        MagicMock(subscription_id="sub-b", display_name="Alpha"),
    ]
    credential_factory = MagicMock(return_value=credential)
    monkeypatch.setattr(init_discovery, "create_default_azure_credential", credential_factory)
    monkeypatch.setattr(
        "azure.mgmt.resource.subscriptions.SubscriptionClient", MagicMock(return_value=client)
    )

    assert init_discovery.list_subscriptions("managed-id") == [
        ("sub-b", "Alpha"),
        ("sub-a", "Zebra"),
    ]
    assert credential_factory.call_args.kwargs["client_id"] == "managed-id"
    client.close.assert_called_once()
    credential.close.assert_called_once()


def test_resource_group_and_location_discovery_use_subscription(monkeypatch) -> None:
    credential = MagicMock()
    resource_client = MagicMock()
    group = MagicMock()
    group.name = "workers"
    resource_client.resource_groups.list.return_value = [group]
    subscription_client = MagicMock()
    location = MagicMock()
    location.name = "uksouth"
    location.display_name = "UK South"
    location.metadata.region_type = "Physical"
    logical_location = MagicMock(name="europe", display_name="Europe")
    logical_location.metadata.region_type = "Logical"
    subscription_client.subscriptions.list_locations.return_value = [location, logical_location]
    monkeypatch.setattr(
        init_discovery, "create_default_azure_credential", MagicMock(return_value=credential)
    )
    resource_factory = MagicMock(return_value=resource_client)
    subscription_factory = MagicMock(return_value=subscription_client)
    monkeypatch.setattr("azure.mgmt.resource.resources.ResourceManagementClient", resource_factory)
    monkeypatch.setattr(
        "azure.mgmt.resource.subscriptions.SubscriptionClient", subscription_factory
    )

    assert init_discovery.list_resource_groups(None, "sub-a") == [("workers", "workers")]
    assert init_discovery.list_locations(None, "sub-a") == [("uksouth", "UK South")]
    assert resource_factory.call_args.args[1] == "sub-a"
    subscription_client.subscriptions.list_locations.assert_called_once_with("sub-a")
