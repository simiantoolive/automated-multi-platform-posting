"""Browser-session account linking for a local, single-process demo."""
import base64
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.config import Settings
from app.schemas import PLATFORM_NAMES, PlatformName, PostingRequest
from app.services.posting_service import publish_all

router = APIRouter(prefix="/ui", tags=["Account connections"])
COOKIE = "publisher_session"


@dataclass
class Session:
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    expires: float = field(default_factory=lambda: time.time() + 8 * 3600)
    connections: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)
    pages: list = field(default_factory=list)
    notice: str = ""


class SessionStore:
    def __init__(self):
        self.items: dict[str, Session] = {}

    def lookup(self, sid):
        now = time.time()
        self.items = {key: item for key, item in self.items.items() if item.expires > now}
        return self.items.get(sid)


def current(request: Request, write=False) -> Session:
    session = request.app.state.sessions.lookup(request.cookies.get(COOKIE))
    if session is None:
        raise HTTPException(401, "Open the account page to start a session.")
    if write:
        token = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(token, session.csrf):
            raise HTTPException(403, "Invalid session request. Refresh the page.")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != request.app.state.settings.app_base_url.rstrip("/"):
            raise HTTPException(403, "This request must come from the local account page.")
    return session


def provider_config(settings, platform):
    if platform == "bluesky":
        return True
    return bool(getattr(settings, platform + "_client_id", "") and
                getattr(settings, platform + "_client_secret").get_secret_value())


def summary(settings, session):
    rows = []
    for name in PLATFORM_NAMES:
        entry = session.connections.get(name)
        expired = bool(entry and entry.get("expires", float("inf")) <= time.time())
        rows.append({"platform": name, "connected": bool(entry) and not expired,
                     "expired": expired, "label": entry["label"] if entry else None,
                     "configured": settings.publish_mode == "mock" or provider_config(settings, name),
                     "mode": settings.publish_mode})
    notice, session.notice = session.notice, ""
    return {"mode": settings.publish_mode, "csrf_token": session.csrf,
            "accounts": rows, "notice": notice,
            "pages": [{"id": p["id"], "name": p.get("name", p["id"])} for p in session.pages]}


@router.get("/session")
async def session_info(request: Request, response: Response):
    store = request.app.state.sessions
    sid = request.cookies.get(COOKIE)
    session = store.lookup(sid)
    if session is None:
        sid, session = secrets.token_urlsafe(32), Session()
        if len(store.items) >= 100:
            raise HTTPException(503, "Too many local sessions. Restart the demo.")
        store.items[sid] = session
        response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=8 * 3600,
                            secure=request.app.state.settings.app_base_url.startswith("https://"))
    response.headers["Cache-Control"] = "no-store"
    return summary(request.app.state.settings, session)


@router.post("/connect/{platform}")
async def connect(platform: PlatformName, request: Request):
    session = current(request, write=True)
    settings = request.app.state.settings
    if settings.publish_mode == "mock":
        session.connections[platform] = {"label": "Demo account · simulated", "values": {}}
        return {"redirect": None}
    if platform == "bluesky":
        return {"app_password_required": True}
    if not provider_config(settings, platform):
        raise HTTPException(409, "The app owner must configure this provider's client ID and secret first.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    redirect = settings.app_base_url.rstrip("/") + f"/ui/callback/{platform}"
    params = {"response_type": "code", "client_id": getattr(settings, platform + "_client_id"),
              "redirect_uri": redirect, "state": state}
    if platform == "facebook":
        url = f"https://www.facebook.com/{settings.facebook_graph_version}/dialog/oauth"
        params["scope"] = "pages_show_list,pages_read_engagement,pages_manage_posts"
    elif platform == "linkedin":
        url = "https://www.linkedin.com/oauth/v2/authorization"
        params["scope"] = "openid profile w_member_social"
    elif platform == "x":
        url = "https://x.com/i/oauth2/authorize"
        params.update(scope="tweet.read tweet.write users.read", code_challenge_method="S256",
                      code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="))
    else:
        url = settings.mastodon_base_url + "/oauth/authorize"
        params["scope"] = "read:accounts write:statuses"
    # Keep only the latest attempt per platform, bounded and short-lived.
    session.pending[platform] = {"state": state, "verifier": verifier,
                                 "redirect": redirect, "expires": time.time() + 600}
    return {"redirect": url + "?" + urlencode(params)}


async def json_request(client, method, url, **kwargs):
    response = await client.request(method, url, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Invalid provider response")
    return data


async def finish_oauth(settings, client, platform, attempt, code):
    client_id = getattr(settings, platform + "_client_id")
    secret = getattr(settings, platform + "_client_secret").get_secret_value()
    form = {"grant_type": "authorization_code", "code": code,
            "redirect_uri": attempt["redirect"], "client_id": client_id}
    if platform == "facebook":
        base = f"https://graph.facebook.com/{settings.facebook_graph_version}"
        token = await json_request(client, "GET", base + "/oauth/access_token",
                                   params={**form, "client_secret": secret})
    elif platform == "linkedin":
        token = await json_request(client, "POST", "https://www.linkedin.com/oauth/v2/accessToken",
                                   data={**form, "client_secret": secret})
    elif platform == "x":
        token = await json_request(client, "POST", "https://api.x.com/2/oauth2/token",
                                   data={**form, "code_verifier": attempt["verifier"]},
                                   auth=httpx.BasicAuth(client_id, secret))
    else:
        token = await json_request(client, "POST", settings.mastodon_base_url + "/oauth/token",
                                   data={**form, "client_secret": secret})
    access = token["access_token"]
    if not isinstance(access, str) or not access:
        raise ValueError("Missing access token")
    headers = {"Authorization": "Bearer " + access}
    expires = time.time() + max(0, int(token.get("expires_in", 8 * 3600)))
    if platform == "facebook":
        data = await json_request(client, "GET", base + "/me/accounts", headers=headers,
                                  params={"fields": "id,name,access_token", "limit": 100})
        pages = [page for page in data["data"] if page.get("access_token") and page.get("id")]
        return {"pages": pages, "expires": expires}
    if platform == "linkedin":
        profile = await json_request(client, "GET", "https://api.linkedin.com/v2/userinfo", headers=headers)
        values = {"linkedin_access_token": access, "linkedin_author_urn": "urn:li:person:" + profile["sub"]}
        label = profile.get("name", "LinkedIn member")
    elif platform == "x":
        profile = (await json_request(client, "GET", "https://api.x.com/2/users/me", headers=headers))["data"]
        values, label = {"x_user_access_token": access}, "@" + profile["username"]
    else:
        profile = await json_request(client, "GET", settings.mastodon_base_url + "/api/v1/accounts/verify_credentials",
                                     headers=headers)
        values, label = {"mastodon_token": access}, profile["acct"]
    return {"values": values, "label": label, "expires": expires}


@router.get("/callback/{platform}", include_in_schema=False)
async def callback(platform: PlatformName, request: Request, state: str = "", code: str = "", error: str = ""):
    session = current(request)
    attempt = session.pending.pop(platform, None)
    if not attempt or attempt["expires"] < time.time() or not secrets.compare_digest(attempt["state"], state):
        raise HTTPException(400, "Invalid or expired connection request. Start again.")
    if error or not code:
        session.notice = "Connection was cancelled or denied. No account was linked."
    else:
        try:
            entry = await finish_oauth(request.app.state.settings, request.app.state.http, platform, attempt, code)
            if platform == "facebook":
                session.pages = entry["pages"]
                session.notice = "Choose the Facebook Page to connect." if session.pages else "No accessible Facebook Pages were returned."
            else:
                session.connections[platform] = entry
                session.notice = "Account connected. No post has been published."
        except Exception:
            session.notice = "Connection failed. Check app permissions and callback configuration, then try again."
    return RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})


class PageChoice(BaseModel):
    page_id: str = Field(min_length=1, max_length=100)


@router.post("/facebook/page")
async def choose_page(body: PageChoice, request: Request):
    session = current(request, write=True)
    page = next((page for page in session.pages if page["id"] == body.page_id), None)
    if not page:
        raise HTTPException(400, "Choose a Page returned by your Facebook connection.")
    session.connections["facebook"] = {"label": page.get("name", page["id"]),
                                       "values": {"facebook_page_id": page["id"],
                                                  "facebook_page_token": page["access_token"]}}
    session.pages = []
    return {"connected": True}


class BlueskyCredentials(BaseModel):
    handle: str = Field(min_length=1, max_length=255)
    app_password: SecretStr


@router.post("/bluesky")
async def connect_bluesky(body: BlueskyCredentials, request: Request):
    session = current(request, write=True)
    settings = request.app.state.settings
    if settings.publish_mode != "real":
        raise HTTPException(409, "Use the demo connection button in mock mode.")
    try:
        data = await json_request(request.app.state.http, "POST",
                                  settings.bluesky_base_url + "/xrpc/com.atproto.server.createSession",
                                  json={"identifier": body.handle, "password": body.app_password.get_secret_value()})
        if not data.get("did") or not data.get("accessJwt"):
            raise ValueError("Invalid session")
    except Exception:
        raise HTTPException(400, "Could not connect. Check your handle, app password and configured PDS.") from None
    session.connections["bluesky"] = {"label": data.get("handle", body.handle),
                                     "values": {"bluesky_handle": body.handle,
                                                "bluesky_app_password": body.app_password.get_secret_value()}}
    return {"connected": True}


@router.delete("/connections/{platform}")
async def disconnect(platform: PlatformName, request: Request):
    session = current(request, write=True)
    session.connections.pop(platform, None)
    session.pending.pop(platform, None)
    if platform == "facebook":
        session.pages = []
    return {"disconnected": True}


class ConnectedPublishRequest(PostingRequest):
    platforms: list[PlatformName] | None = Field(default=None, min_length=1, max_length=5)

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Select each platform only once")
        return value


@router.post("/publish")
async def publish_connected(body: ConnectedPublishRequest, request: Request):
    session = current(request, write=True)
    selected = body.platforms if body.platforms is not None else [
        name for name in PLATFORM_NAMES if name in session.connections
        and session.connections[name].get("expires", float("inf")) > time.time()]
    if not selected:
        raise HTTPException(409, "Connect and select at least one account before publishing.")
    missing = [name for name in selected if name not in session.connections
               or session.connections[name].get("expires", float("inf")) <= time.time()]
    if missing:
        raise HTTPException(409, "Selected accounts are missing or expired: " + ", ".join(missing))
    # Never inherit another account's server-level posting credentials for this UI.
    settings = request.app.state.settings
    values = settings.model_dump()
    for key in ("facebook_page_token", "linkedin_access_token", "x_user_access_token",
                "mastodon_token", "bluesky_app_password"):
        values[key] = ""
    values.update(facebook_page_id="", linkedin_author_urn="", bluesky_handle="")
    for name in selected:
        values.update(session.connections[name]["values"])
    connected_settings = Settings(_env_file=None, **values)
    return await publish_all(connected_settings, request.app.state.http, body.message, selected, str(uuid4()))


class HideCallbackQuery(logging.Filter):
    """Authorization codes must not appear in Uvicorn's access log."""
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].startswith("/ui/callback/"):
                args[2] = args[2].split("?", 1)[0]
                record.args = tuple(args)
        return True
