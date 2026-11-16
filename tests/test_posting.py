"""Contract and adapter tests. Every third-party HTTP response is simulated."""
import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.schemas import PLATFORM_NAMES, PostingRequest, PublishRequest

SECRET = "test-only-credential"
MESSAGE = "Hello 🌍"
CTA = "https://example.com"
CONTENT = f"{MESSAGE} {CTA}"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def configured(**overrides):
    values = dict(
        _env_file=None, publish_mode="real", facebook_page_id="123",
        facebook_page_token=SECRET, linkedin_author_urn="urn:li:person:abc",
        linkedin_access_token=SECRET, x_user_access_token=SECRET,
        mastodon_token=SECRET, bluesky_handle="test.bsky.social",
        bluesky_app_password=SECRET,
    )
    values.update(overrides)
    return Settings(**values)


def upstream(request):
    path = request.url.path
    if path.endswith("/feed"):
        return httpx.Response(200, json={"id": "123_456"})
    if path.endswith("/123_456"):
        return httpx.Response(200, json={"permalink_url": "https://www.facebook.com/123/posts/456"})
    if path == "/rest/posts":
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:456"})
    if path == "/2/tweets":
        return httpx.Response(201, json={"data": {"id": "789", "text": CONTENT}})
    if path == "/api/v1/statuses":
        return httpx.Response(200, json={"id": "456", "url": "https://mastodon.social/@test/456",
                                       "visibility": "public"})
    if path.endswith("createSession"):
        return httpx.Response(200, json={"accessJwt": SECRET, "did": "did:plc:test"})
    if path.endswith("createRecord"):
        return httpx.Response(200, json={"uri": "at://did:plc:test/app.bsky.feed.post/abc"})
    raise AssertionError(f"Unexpected request: {path}")


def post(handler=upstream, settings=None, payload=None, route="/api/v1/publish"):
    with TestClient(create_app(settings or configured(), httpx.MockTransport(handler))) as client:
        return client.post(route, json=payload if payload is not None else {"message": MESSAGE, "cta_url": CTA})


def test_five_successes_and_payloads():
    calls = []
    def handler(request):
        calls.append(request)
        return upstream(request)
    response = post(handler)
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "real"
    assert data["success"] is True
    assert (data["success_count"], data["failure_count"], data["total_count"]) == (5, 0, 5)
    assert [r["platform"] for r in data["results"]] == list(PLATFORM_NAMES)
    assert all(r["public_access"] is None for r in data["results"])
    assert all(r["time"].endswith("Z") and r["post_id"] for r in data["results"])
    by_path = {r.url.path: r for r in calls}
    bodies = {path: json.loads(r.content) for path, r in by_path.items() if r.content}
    assert bodies["/v27.0/123/feed"] == {"message": CONTENT, "published": True}
    assert bodies["/rest/posts"]["commentary"] == CONTENT
    assert bodies["/rest/posts"]["author"] == "urn:li:person:abc"
    assert bodies["/rest/posts"]["lifecycleState"] == "PUBLISHED"
    assert by_path["/rest/posts"].headers["linkedin-version"] == "202609"
    assert by_path["/rest/posts"].headers["x-restli-protocol-version"] == "2.0.0"
    assert bodies["/2/tweets"] == {"text": CONTENT}
    assert bodies["/api/v1/statuses"] == {"status": CONTENT, "visibility": "public"}
    record = bodies["/xrpc/com.atproto.repo.createRecord"]["record"]
    facet = record["facets"][0]
    assert record["text"].encode()[facet["index"]["byteStart"]:facet["index"]["byteEnd"]].decode() == CTA
    assert all(r.headers["authorization"] == f"Bearer {SECRET}" for r in calls
               if not r.url.path.endswith("createSession"))
    linkedin = data["results"][1]
    assert linkedin["posted_url"] is None  # No guessed permalink from its URN.
    assert data["results"][2]["url_source"] == "derived_from_id"


@pytest.mark.parametrize("payload", [
    {}, {"message": MESSAGE}, {"cta_url": CTA}, {"message": "", "cta_url": CTA},
    {"message": " ", "cta_url": CTA}, {"message": 42, "cta_url": CTA},
    {"message": "See https://other.example", "cta_url": CTA},
    {"message": "See www.other.example", "cta_url": CTA},
    {"message": MESSAGE, "cta_url": "ftp://example.com"},
    {"message": MESSAGE, "cta_url": "https:///example.com"},
    {"message": MESSAGE, "cta_url": "https://"},
    {"message": MESSAGE, "cta_url": "https://localhost"},
    {"message": MESSAGE, "cta_url": "https://user:password@example.com"},
    {"message": MESSAGE, "cta_url": "https://example.com/a b"},
    {"message": MESSAGE, "cta_url": "https://example.com/%ZZ"},
    {"message": MESSAGE, "cta_url": "https://example.com/https://other.example"},
    {"message": MESSAGE, "cta_url": CTA, "platforms": []},
    {"message": MESSAGE, "cta_url": CTA, "platforms": ["unknown"]},
    {"message": MESSAGE, "cta_url": CTA, "platforms": ["x", "x"]},
    {"message": MESSAGE, "cta_url": CTA, "mode": "mock"},
])
def test_invalid_input_never_contacts_platforms(payload):
    calls = []
    def handler(request):
        calls.append(request)
        return upstream(request)
    response = post(handler, payload=payload)
    assert response.status_code == 422
    assert response.json()["detail"]
    assert not calls


def test_combined_200_boundary():
    valid = {"message": "a" * (199 - len(CTA)), "cta_url": CTA}
    assert len(PublishRequest(**valid).content) == 200
    assert post(payload=valid).json()["success"]
    invalid = {**valid, "message": valid["message"] + "a"}
    assert post(payload=invalid).status_code == 422


def test_original_contract_all_platforms():
    response = post(route="/posting", payload={"message": CONTENT})
    assert response.json()["total_count"] == 5
    assert response.json()["success"]
    assert post(route="/posting", payload={"message": CONTENT, "platforms": ["x"]}).status_code == 422


@pytest.mark.parametrize("message", ["no url", "https://a.example https://b.example", " " * 10,
                                     "x" * 201, "http:///broken.example"])
def test_original_invalid(message):
    assert post(route="/posting", payload={"message": message}).status_code == 422


def test_select_one_platform():
    calls = []
    def handler(request):
        calls.append(request)
        return upstream(request)
    data = post(handler, payload={"message": MESSAGE, "cta_url": CTA, "platforms": ["x"]}).json()
    assert data["total_count"] == data["success_count"] == 1
    assert [r.url.path for r in calls] == ["/2/tweets"]


@pytest.mark.parametrize("status,code", [
    (401, "authentication_failed"), (403, "permission_denied"), (402, "access_payment_required"),
    (429, "rate_limited"), (500, "upstream_unavailable"), (400, "api_error"),
])
def test_http_failure_does_not_stop_others(status, code, caplog):
    caplog.set_level(logging.INFO, logger="publisher")
    def handler(request):
        if request.url.path == "/2/tweets":
            return httpx.Response(status, text=SECRET, headers={"Retry-After": "30"})
        return upstream(request)
    response = post(handler)
    data = response.json()
    assert data["success"] is False
    assert (data["success_count"], data["failure_count"]) == (4, 1)
    error = data["results"][2]["error"]
    assert error["code"] == code
    assert error["http_status"] == status
    assert error["retry_after_seconds"] == 30
    assert SECRET not in response.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("kind", ["timeout", "network", "malformed"])
def test_transport_failures(kind):
    def handler(request):
        if request.url.path == "/2/tweets":
            if kind == "timeout":
                raise httpx.ReadTimeout(SECRET, request=request)
            if kind == "network":
                raise httpx.ConnectError(SECRET, request=request)
            return httpx.Response(200, text=SECRET)
        return upstream(request)
    data = post(handler).json()
    assert data["success_count"] == 4
    assert data["results"][2]["error"]["outcome_unknown"] is True
    assert data["results"][2]["posted_url"] is None
    assert data["results"][2]["date"] is None


def test_real_mode_missing_credentials_never_becomes_mock():
    data = post(settings=Settings(_env_file=None)).json()
    assert data["mode"] == "real"
    assert data["failure_count"] == 5
    assert data["simulated_count"] == 0
    assert all(r["error"]["code"] == "missing_configuration" for r in data["results"])


def test_mock_mode_no_network_or_fake_publication_evidence():
    calls = []
    def handler(request):
        calls.append(request)
        raise AssertionError("Mock mode must not use HTTP")
    data = post(handler, settings=configured(publish_mode="mock")).json()
    assert not calls
    assert data["mode"] == "mock"
    assert data["success"] is False
    assert (data["success_count"], data["failure_count"], data["simulated_count"]) == (0, 0, 5)
    for result in data["results"]:
        assert result["mode"] == "mock"
        assert result["status"] == "simulated"
        assert all(result[k] is None for k in ("post_id", "posted_url", "public_access", "date", "time"))


def test_facebook_permalink_failure_preserves_publish_success():
    def handler(request):
        if request.method == "GET":
            raise httpx.ReadTimeout(SECRET, request=request)
        return upstream(request)
    result = post(handler).json()["results"][0]
    assert result["status"] == "success"
    assert result["posted_url"] is None
    assert result["warnings"]


def test_total_timeout_after_facebook_publish_preserves_success():
    async def handler(request):
        if request.method == "GET":
            await asyncio.sleep(0.2)
        return upstream(request)
    result = post(handler, configured(platform_timeout_seconds=0.05)).json()["results"][0]
    assert result["status"] == "success"
    assert result["post_id"] == "123_456"
    assert result["posted_url"] is None
    assert result["warnings"]


@pytest.mark.parametrize("path,payload", [
    ("/2/tweets", {"data": {}}),
    ("/api/v1/statuses", {"url": "https://example.com"}),
    ("/xrpc/com.atproto.repo.createRecord", {"uri": "at://wrong/app.bsky.feed.post/fake"}),
])
def test_malformed_post_ids_do_not_create_urls(path, payload):
    def handler(request):
        return httpx.Response(200, json=payload) if request.url.path == path else upstream(request)
    data = post(handler).json()
    failures = [r for r in data["results"] if r["status"] == "failed"]
    assert len(failures) == 1
    assert failures[0]["posted_url"] is None


def test_empty_linkedin_body_and_missing_id_header():
    def handler(request):
        if request.url.path == "/rest/posts":
            return httpx.Response(201)
        return upstream(request)
    result = post(handler).json()["results"][1]
    assert result["status"] == "failed"
    assert result["error"]["outcome_unknown"]


def test_platforms_run_concurrently_and_total_timeout_isolated():
    arrived = set()
    async def handler(request):
        if request.url.path == "/2/tweets":
            await asyncio.sleep(0.2)
        arrived.add(request.url.host)
        return upstream(request)
    data = post(handler, configured(platform_timeout_seconds=0.05)).json()
    assert data["success_count"] == 4
    assert data["results"][2]["error"]["code"] == "timeout"
    assert len(arrived) == 4


def test_health_and_openapi():
    with TestClient(create_app(configured(publish_mode="mock"))) as client:
        assert client.get("/health").json() == {"status": "ok", "mode": "mock"}
        assert client.get("/docs").status_code == 200
        paths = client.get("/openapi.json").json()["paths"]
        assert "/posting" in paths and "/api/v1/publish" in paths


@pytest.mark.parametrize("origin", ["http://mastodon.social", "https://user:pass@mastodon.social",
                                    "https://mastodon.social/path", "https://mastodon.social?token=secret"])
def test_platform_origins_must_use_https_without_secrets(origin):
    with pytest.raises(ValidationError):
        configured(mastodon_base_url=origin)
