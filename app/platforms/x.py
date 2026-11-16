"""X API v2 with OAuth 2.0 Authorization Code/PKCE user-context access token."""
import httpx
from app.errors import PlatformError
from app.platforms.base import BaseAdapter, Published, object_body, request, required, response_id


class X(BaseAdapter):
    name = "x"

    async def publish(self, client: httpx.AsyncClient, message: str) -> Published:
        token = required(self.settings.x_user_access_token, "X_USER_ACCESS_TOKEN")
        body = object_body(await request(client, "POST", "https://api.x.com/2/tweets",
                                         headers={"Authorization": f"Bearer {token}"},
                                         json={"text": message}))
        post_id = response_id(body["data"])
        if not post_id.isdigit():
            raise PlatformError("unexpected_response", "X returned an invalid post ID.", outcome_unknown=True)
        return Published(post_id, f"https://x.com/i/web/status/{post_id}", "derived_from_id")
