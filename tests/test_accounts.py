"""Offline account-linking tests; OAuth providers are simulated."""
import time
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.api.accounts import COOKIE
from app.schemas import PLATFORM_NAMES


def config(**overrides):
    values = dict(_env_file=None, publish_mode="real", facebook_client_id="fb",
                  facebook_client_secret="owner-secret", linkedin_client_id="li",
                  linkedin_client_secret="owner-secret", x_client_id="x",
                  x_client_secret="owner-secret", mastodon_client_id="ma",
                  mastodon_client_secret="owner-secret")
    values.update(overrides)
    return Settings(**values)


def headers(client):
    return {"x-csrf-token": client.get("/ui/session").json()["csrf_token"]}


def callback_url(client, platform, csrf):
    response = client.post(f"/ui/connect/{platform}", headers=csrf)
    assert response.status_code == 200
    query = parse_qs(urlsplit(response.json()["redirect"]).query)
    return f"/ui/callback/{platform}?code=one-use-code&state={query['state'][0]}"


def oauth(request):
    path = request.url.path
    if path.endswith("/oauth/access_token") or path.endswith("/accessToken") or path.endswith("/token"):
        return httpx.Response(200, json={"access_token": "user-secret", "expires_in": 3600})
    if path.endswith("/userinfo"):
        return httpx.Response(200, json={"sub": "member123", "name": "Demo member"})
    if path.endswith("/users/me"):
        return httpx.Response(200, json={"data": {"id": "123", "username": "demo"}})
    if path.endswith("/verify_credentials"):
        return httpx.Response(200, json={"id": "123", "acct": "demo@mastodon.social"})
    if path.endswith("/me/accounts"):
        return httpx.Response(200, json={"data": [{"id": "123", "name": "My Page", "access_token": "page-secret"}]})
    if path.endswith("createSession"):
        return httpx.Response(200, json={"did": "did:plc:test", "handle": "demo.bsky.social", "accessJwt": "bsky-secret"})
    return httpx.Response(500)


def test_mock_connect_all_publish_disconnect_without_network():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(500)
    with TestClient(create_app(config(publish_mode="mock"), httpx.MockTransport(handler))) as client:
        csrf = headers(client)
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.post("/ui/publish", headers=csrf, json={"message": "Hello https://example.com"}).status_code == 409
        for platform in PLATFORM_NAMES:
            assert client.post("/ui/connect/" + platform, headers=csrf).status_code == 200
        response = client.post("/ui/publish", headers=csrf, json={"message": "Hello https://example.com"})
        assert response.json()["simulated_count"] == 5
        assert response.json()["success_count"] == 0
        assert client.delete("/ui/connections/linkedin", headers=csrf).status_code == 200
        assert client.post("/ui/publish", headers=csrf, json={"message": "Hello https://example.com"}).json()["simulated_count"] == 4
    assert calls == []


def test_session_cookie_csrf_and_origin_guards():
    with TestClient(create_app(config(publish_mode="mock"))) as client:
        response = client.get("/ui/session")
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/ui/connect/x").status_code == 403
        csrf = {"x-csrf-token": response.json()["csrf_token"], "origin": "https://evil.example"}
        assert client.post("/ui/connect/x", headers=csrf).status_code == 403


@pytest.mark.parametrize("platform", ["facebook", "linkedin", "x", "mastodon"])
def test_oauth_connect_and_no_secret_exposure(platform):
    with TestClient(create_app(config(), httpx.MockTransport(oauth))) as client:
        csrf = headers(client)
        callback = callback_url(client, platform, csrf)
        response = client.get(callback, follow_redirects=False)
        assert response.status_code == 303
        if platform == "facebook":
            listing = client.get("/ui/session")
            assert listing.json()["pages"] == [{"id": "123", "name": "My Page"}]
            assert "page-secret" not in listing.text
            assert client.post("/ui/facebook/page", headers=csrf, json={"page_id": "not-mine"}).status_code == 400
            assert client.post("/ui/facebook/page", headers=csrf, json={"page_id": "123"}).status_code == 200
        status = client.get("/ui/session")
        assert next(a for a in status.json()["accounts"] if a["platform"] == platform)["connected"]
        assert "user-secret" not in status.text and "owner-secret" not in status.text
        assert client.get(callback).status_code == 400  # State cannot be reused.


def test_oauth_state_bound_to_browser():
    app = create_app(config(), httpx.MockTransport(oauth))
    with TestClient(app) as first, TestClient(app) as second:
        url = callback_url(first, "linkedin", headers(first))
        headers(second)
        assert second.get(url).status_code == 400
        assert first.get(url, follow_redirects=False).status_code == 303


def test_missing_developer_configuration_is_not_fake_connection():
    with TestClient(create_app(config(linkedin_client_id=""))) as client:
        csrf = headers(client)
        assert client.post("/ui/connect/linkedin", headers=csrf).status_code == 409
        assert not next(a for a in client.get("/ui/session").json()["accounts"] if a["platform"] == "linkedin")["connected"]


def test_denial_does_not_link_account():
    with TestClient(create_app(config(), httpx.MockTransport(oauth))) as client:
        url = callback_url(client, "linkedin", headers(client)).replace("code=one-use-code", "error=access_denied")
        assert client.get(url, follow_redirects=False).status_code == 303
        result = client.get("/ui/session").json()
        assert not any(a["connected"] for a in result["accounts"])
        assert "cancelled" in result["notice"]


def test_bluesky_password_is_not_returned():
    with TestClient(create_app(config(), httpx.MockTransport(oauth))) as client:
        csrf = headers(client)
        response = client.post("/ui/bluesky", headers=csrf, json={"handle": "demo.bsky.social", "app_password": "private-password"})
        assert response.status_code == 200
        status = client.get("/ui/session")
        assert "private-password" not in status.text
        assert status.json()["accounts"][-1]["connected"]


def test_expired_connection_blocks_publish():
    app = create_app(config(publish_mode="mock"))
    with TestClient(app) as client:
        csrf = headers(client)
        for platform in PLATFORM_NAMES:
            client.post("/ui/connect/" + platform, headers=csrf)
        app.state.sessions.items[client.cookies[COOKIE]].connections["x"]["expires"] = time.time() - 1
        assert client.post("/ui/publish", headers=csrf, json={"message": "Hi https://example.com", "platforms": ["x"]}).status_code == 409


def test_linked_posting_does_not_fall_back_to_owner_credentials():
    app = create_app(config(x_user_access_token="owner-account-token"), httpx.MockTransport(oauth))
    with TestClient(app) as client:
        csrf = headers(client)
        session = app.state.sessions.items[client.cookies[COOKIE]]
        for name in PLATFORM_NAMES:
            session.connections[name] = {"label": "empty fixture", "values": {}}
        data = client.post("/ui/publish", headers=csrf, json={"message": "Hi https://example.com"}).json()
        assert data["failure_count"] == 5
        assert all(r["error"]["code"] == "missing_configuration" for r in data["results"])


def test_publish_only_browser_linked_bluesky():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("createRecord"):
            return httpx.Response(200, json={"uri": "at://did:plc:test/app.bsky.feed.post/abc"})
        return oauth(request)
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        csrf = headers(client)
        assert client.post("/ui/bluesky", headers=csrf, json={"handle": "demo.bsky.social", "app_password": "private-password"}).status_code == 200
        result = client.post("/ui/publish", headers=csrf, json={"message": "Hi https://example.com", "platforms": ["bluesky"]})
        assert result.status_code == 200
        assert result.json()["success_count"] == result.json()["total_count"] == 1
        assert result.json()["results"][0]["platform"] == "bluesky"
    assert all(path.startswith("/xrpc/") for path in calls)


@pytest.mark.parametrize("platforms", [[], ["unknown"], ["bluesky", "bluesky"]])
def test_invalid_browser_platform_selection(platforms):
    with TestClient(create_app(config(publish_mode="mock"))) as client:
        csrf = headers(client)
        assert client.post("/ui/publish", headers=csrf, json={"message": "Hi https://example.com", "platforms": platforms}).status_code == 422


def test_only_selected_connections_are_used():
    with TestClient(create_app(config(publish_mode="mock"))) as client:
        csrf = headers(client)
        for name in ["bluesky", "linkedin"]:
            client.post("/ui/connect/" + name, headers=csrf)
        data = client.post("/ui/publish", headers=csrf, json={"message": "Hi https://example.com", "platforms": ["bluesky"]}).json()
        assert [r["platform"] for r in data["results"]] == ["bluesky"]
        assert client.post("/ui/publish", headers=csrf, json={"message": "Hi https://example.com", "platforms": ["x"]}).status_code == 409
