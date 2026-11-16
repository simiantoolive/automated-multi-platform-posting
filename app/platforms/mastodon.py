"""Mastodon status API using the account's own instance."""
import httpx
from app.platforms.base import BaseAdapter, Published, api_url, object_body, request, required, response_id


class Mastodon(BaseAdapter):
    name = "mastodon"

    async def publish(self, client: httpx.AsyncClient, message: str) -> Published:
        token = required(self.settings.mastodon_token, "MASTODON_TOKEN")
        data = object_body(await request(client, "POST", self.settings.mastodon_base_url + "/api/v1/statuses",
                                         headers={"Authorization": f"Bearer {token}"},
                                         json={"status": message, "visibility": "public"}))
        post_id = response_id(data)
        url = api_url(data.get("url"))
        return Published(post_id, url, "api" if url else None)
