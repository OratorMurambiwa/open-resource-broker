"""Read-only Azure account discovery for the interactive init wizard."""

from orb.infrastructure.adapters.logging_adapter import LoggingAdapter
from orb.providers.azure.infrastructure.credential_factory import create_default_azure_credential


def list_subscriptions(client_id: str | None) -> list[tuple[str, str]]:
    """List subscriptions visible to the selected Azure identity."""
    from azure.mgmt.resource.subscriptions import SubscriptionClient

    credential = create_default_azure_credential(client_id=client_id, logger=LoggingAdapter())
    try:
        client = SubscriptionClient(credential)
        try:
            return sorted(
                (
                    subscription.subscription_id,
                    subscription.display_name or subscription.subscription_id,
                )
                for subscription in client.subscriptions.list()
                if subscription.subscription_id
            )
        finally:
            client.close()
    finally:
        credential.close()


def list_resource_groups(client_id: str | None, subscription_id: str) -> list[tuple[str, str]]:
    """List resource groups in the selected subscription."""
    from azure.mgmt.resource.resources import ResourceManagementClient

    credential = create_default_azure_credential(client_id=client_id, logger=LoggingAdapter())
    try:
        client = ResourceManagementClient(credential, subscription_id)
        try:
            return sorted(
                (group.name, group.name) for group in client.resource_groups.list() if group.name
            )
        finally:
            client.close()
    finally:
        credential.close()


def list_locations(client_id: str | None, subscription_id: str) -> list[tuple[str, str]]:
    """List locations available to the selected subscription."""
    from azure.mgmt.resource.subscriptions import SubscriptionClient

    credential = create_default_azure_credential(client_id=client_id, logger=LoggingAdapter())
    try:
        client = SubscriptionClient(credential)
        try:
            return sorted(
                (location.name, location.display_name or location.name)
                for location in client.subscriptions.list_locations(subscription_id)
                if location.name
            )
        finally:
            client.close()
    finally:
        credential.close()
