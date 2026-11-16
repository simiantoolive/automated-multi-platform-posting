"""LinkedIn versioned Posts API; accepts user OAuth tokens, not app-only tokens."""
import re
from urllib.parse import unquote
import httpx
from app.errors import PlatformError
from app.platforms.base import BaseAdapter, Published, request, required


class LinkedIn(BaseAdapter):
    name = "linkedin"

    async def publish(self, client: httpx.AsyncClient, message: str) -> Published:
        token = required(self.settings.linkedin_access_token, "LINKEDIN_ACCESS_TOKEN")
        author = required(self.settings.linkedin_author_urn, "LINKEDIN_AUTHOR_URN")
        if not re.fullmatch(r"urn:li:(person|organization):[A-Za-z0-9_-]+", author):
            raise PlatformError("invalid_configuration", "LINKEDIN_AUTHOR_URN must identify a person or organization.")
        response = await request(client, "POST", "https://api.linkedin.com/rest/posts",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Linkedin-Version": self.settings.linkedin_api_version,
                                          "X-Restli-Protocol-Version": "2.0.0"},
                                 json={"author": author, "commentary": message, "visibility": "PUBLIC",
                                       "distribution": {"feedDistribution": "MAIN_FEED",
                                                        "targetEntities": [], "thirdPartyDistributionChannels": []},
                                       "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False})
        post_id = unquote(response.headers.get("x-restli-id", ""))
        if not re.fullmatch(r"urn:li:(share|ugcPost):[0-9]+", post_id):
            raise PlatformError("unexpected_response", "LinkedIn did not return a valid post URN.", outcome_unknown=True)
        # The API returns a URN, not a confirmed browser permalink.
        return Published(post_id, warnings=("LinkedIn returned a post URN; no browser permalink was verified.",))
