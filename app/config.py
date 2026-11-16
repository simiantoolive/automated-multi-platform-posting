"""Environment-only configuration; tokens are masked in representations."""
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    publish_mode: Literal["real", "mock"] = "real"
    app_base_url: str = "http://localhost:4000"
    facebook_client_id: str = ""
    facebook_client_secret: SecretStr = SecretStr("")
    linkedin_client_id: str = ""
    linkedin_client_secret: SecretStr = SecretStr("")
    x_client_id: str = ""
    x_client_secret: SecretStr = SecretStr("")
    mastodon_client_id: str = ""
    mastodon_client_secret: SecretStr = SecretStr("")
    http_timeout_seconds: float = Field(default=10, gt=0, le=30)
    platform_timeout_seconds: float = Field(default=35, gt=0, le=90)
    facebook_graph_version: str = Field(default="v27.0", pattern=r"^v[0-9]+\.[0-9]+$")
    facebook_page_id: str = ""
    facebook_page_token: SecretStr = SecretStr("")
    linkedin_api_version: str = Field(default="202609", pattern=r"^[0-9]{6}$")
    linkedin_author_urn: str = ""
    linkedin_access_token: SecretStr = SecretStr("")
    x_user_access_token: SecretStr = SecretStr("")
    mastodon_base_url: str = "https://mastodon.social"
    mastodon_token: SecretStr = SecretStr("")
    bluesky_base_url: str = "https://bsky.social"
    bluesky_handle: str = ""
    bluesky_app_password: SecretStr = SecretStr("")

    @field_validator("mastodon_base_url", "bluesky_base_url")
    @classmethod
    def https_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("Platform base URL must be an HTTPS origin without credentials")
        return value.rstrip("/")
