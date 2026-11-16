"""AT Protocol post creation with UTF-8 link facets."""
from datetime import datetime, timezone
import re
import httpx
from app.errors import PlatformError
from app.platforms.base import BaseAdapter, Published, object_body, request, required, response_id
from app.schemas import message_url


class Bluesky(BaseAdapter):
    name = "bluesky"

    async def publish(self, client: httpx.AsyncClient, message: str) -> Published:
        handle = required(self.settings.bluesky_handle, "BLUESKY_HANDLE")
        password = required(self.settings.bluesky_app_password, "BLUESKY_APP_PASSWORD")
        base = self.settings.bluesky_base_url + "/xrpc/"
        session = object_body(await request(client, "POST", base + "com.atproto.server.createSession",
                                            json={"identifier": handle, "password": password}))
        did = session["did"]
        url, start, end = message_url(message)
        record = {"$type": "app.bsky.feed.post", "text": message,
                  "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                  "facets": [{"index": {"byteStart": len(message[:start].encode("utf-8")),
                                        "byteEnd": len(message[:end].encode("utf-8"))},
                              "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}]}
        data = object_body(await request(client, "POST", base + "com.atproto.repo.createRecord",
                                         headers={"Authorization": "Bearer " + session["accessJwt"]},
                                         json={"repo": did, "collection": "app.bsky.feed.post", "record": record}))
        uri = response_id(data, "uri")
        match = re.fullmatch(r"at://(did:[a-z]+:[A-Za-z0-9._:%-]+)/app\.bsky\.feed\.post/([A-Za-z0-9_-]+)", uri)
        if not match or match[1] != did:
            raise PlatformError("unexpected_response", "Bluesky returned an invalid record URI.", outcome_unknown=True)
        return Published(uri, f"https://bsky.app/profile/{did}/post/{match[2]}", "derived_from_id")
