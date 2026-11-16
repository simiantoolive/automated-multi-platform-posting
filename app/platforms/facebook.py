"""Facebook Page feed publishing with a Page access token."""
import re
import httpx
from app.errors import PlatformError
from app.platforms.base import BaseAdapter, Published, api_url, object_body, request, required, response_id


class Facebook(BaseAdapter):
    name = "facebook"

    async def publish(self, client: httpx.AsyncClient, message: str) -> Published:
        page = required(self.settings.facebook_page_id, "FACEBOOK_PAGE_ID")
        token = required(self.settings.facebook_page_token, "FACEBOOK_PAGE_TOKEN")
        if not page.isdigit():
            raise PlatformError("invalid_configuration", "FACEBOOK_PAGE_ID must be numeric.")
        base = f"https://graph.facebook.com/{self.settings.facebook_graph_version}"
        headers = {"Authorization": f"Bearer {token}"}
        data = object_body(await request(client, "POST", f"{base}/{page}/feed",
                                         headers=headers, json={"message": message, "published": True}))
        post_id = response_id(data)
        if not re.fullmatch(r"[0-9]+_[0-9]+", post_id):
            raise PlatformError("unexpected_response", "Facebook returned an invalid post ID.", outcome_unknown=True)
        self.acknowledged = Published(post_id, warnings=("Published, but metadata lookup did not complete.",))
        # The POST already succeeded. A metadata failure must not be reported as a failed publish.
        try:
            result = object_body(await request(client, "GET", f"{base}/{post_id}",
                                               headers=headers, params={"fields": "permalink_url"}))
            url = api_url(result.get("permalink_url"))
        except Exception:
            url = None
        warnings = () if url else ("Published, but the permalink was unavailable.",)
        return Published(post_id, url, "api" if url else None, warnings)
