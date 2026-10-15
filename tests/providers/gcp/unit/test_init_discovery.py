"""GCP init discovery reads paginated project and region listings."""

from unittest.mock import MagicMock

from orb.providers.gcp.services import init_discovery


def test_project_search_pages_and_closes_session(monkeypatch) -> None:
    session = MagicMock()
    first = MagicMock()
    first.json.return_value = {
        "projects": [{"projectId": "project-b", "displayName": "B", "state": "ACTIVE"}],
        "nextPageToken": "next",
    }
    second = MagicMock()
    second.json.return_value = {
        "projects": [
            {"projectId": "project-a", "displayName": "A", "state": "ACTIVE"},
            {"projectId": "deleted", "state": "DELETE_REQUESTED"},
        ]
    }
    session.get.side_effect = [first, second]
    monkeypatch.setattr("google.auth.default", lambda **_kwargs: (object(), None))
    monkeypatch.setattr(
        "google.auth.transport.requests.AuthorizedSession", MagicMock(return_value=session)
    )

    assert init_discovery.list_projects() == [("project-a", "A"), ("project-b", "B")]
    assert session.get.call_args_list[0].kwargs["params"] is None
    assert session.get.call_args_list[1].kwargs["params"] == {"pageToken": "next"}
    session.close.assert_called_once()


def test_regions_use_selected_project(monkeypatch) -> None:
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "items": [
            {"name": "europe-west2", "status": "UP"},
            {"name": "us-central1", "status": "DOWN"},
        ]
    }
    session.get.return_value = response
    auth_default = MagicMock(return_value=(object(), None))
    monkeypatch.setattr("google.auth.default", auth_default)
    monkeypatch.setattr(
        "google.auth.transport.requests.AuthorizedSession", MagicMock(return_value=session)
    )

    assert init_discovery.list_regions("selected-project") == [("europe-west2", "europe-west2")]
    assert "/projects/selected-project/regions" in session.get.call_args.args[0]
    assert auth_default.call_args.kwargs["scopes"] == [
        "https://www.googleapis.com/auth/cloud-platform"
    ]
    session.close.assert_called_once()
