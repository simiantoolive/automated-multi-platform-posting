"""Common adapter interface and small HTTP helpers."""
from dataclasses import dataclass
from typing import Literal, Protocol
import httpx
from pydantic import SecretStr
from app.config import Settings
from app.errors import PlatformError
from app.schemas import PlatformName, validate_cta


def required(value: str | SecretStr, name: str) -> str:
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    if not raw.strip():
        raise PlatformError("missing_configuration", f"Missing configuration: {name}")
    return raw


@dataclass(frozen=True)
class Published:
    post_id: str
    url: str | None = None
    url_source: Literal["api", "derived_from_id"] | None = None
    warnings: tuple[str, ...] = ()


class Platform(Protocol):
    name: PlatformName
    async def publish(self, client: httpx.AsyncClient, message: str) -> Published: ...


class BaseAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.acknowledged: Published | None = None


async def request(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    response.raise_for_status()
    return response


def object_body(response: httpx.Response) -> dict:
    data = response.json()
    if not isinstance(data, dict):
        raise PlatformError("unexpected_response", "Platform returned an invalid response.", outcome_unknown=True)
    return data


def response_id(data: dict, key: str = "id") -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PlatformError("unexpected_response", "Platform did not return a post identifier.", outcome_unknown=True)
    return value


def api_url(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return validate_cta(value)
    except ValueError:
        return None
