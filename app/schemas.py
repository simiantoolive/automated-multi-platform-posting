"""Shared request validation and explicit real/mock result contracts."""
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator, model_validator

PlatformName = Literal["facebook", "linkedin", "x", "mastodon", "bluesky"]
PLATFORM_NAMES: tuple[PlatformName, ...] = ("facebook", "linkedin", "x", "mastodon", "bluesky")
LINK_PATTERN = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>\"]+", re.I)


def validate_cta(value: str) -> str:
    if not value or re.search(r'[\s<>\x00-\x1f\x7f\\]', value):
        raise ValueError("CTA URL must not contain whitespace, control characters or backslashes")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValueError("CTA URL must be an absolute HTTP or HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("CTA URL must not contain credentials")
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("CTA URL contains an invalid percent escape")
    validated = TypeAdapter(HttpUrl).validate_python(value)
    if not validated.host or ("." not in validated.host and ":" not in validated.host):
        raise ValueError("CTA URL must have a qualified hostname or IP address")
    return value  # Keep the exact published characters, not a normalized URL.


def message_url(message: str) -> tuple[str, int, int]:
    matches = list(LINK_PATTERN.finditer(message))
    if len(matches) != 1 or len(re.findall(r"[a-z][a-z0-9+.-]*://", message, re.I)) != 1:
        raise ValueError("Published content must include exactly one HTTP/HTTPS CTA URL")
    match = matches[0]
    url = match.group().rstrip(".,!?;")
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    validate_cta(url)
    return url, match.start(), match.start() + len(url)


class PostingRequest(BaseModel):
    """Original assignment: URL is embedded and all five platforms are internal."""
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=200, strict=True)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        message_url(value)
        return value


class PublishRequest(BaseModel):
    """Convenience extension; combined content obeys the original length limit."""
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=200, strict=True)
    cta_url: str = Field(min_length=1, max_length=200, strict=True)
    platforms: list[PlatformName] | None = Field(default=None, min_length=1, max_length=5)

    @field_validator("message")
    @classmethod
    def text_without_links(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        if LINK_PATTERN.search(value):
            raise ValueError("Put the single CTA link in cta_url, not in message")
        return value

    @field_validator("cta_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return validate_cta(value)

    @field_validator("platforms")
    @classmethod
    def unique_platforms(cls, value):
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Platform selections must be unique")
        return value

    @model_validator(mode="after")
    def combined_limit(self):
        PostingRequest(message=self.content)
        return self

    @property
    def content(self) -> str:
        return f"{self.message} {self.cta_url}"


class ErrorDetail(BaseModel):
    code: str
    message: str
    http_status: int | None = None
    retry_after_seconds: int | None = None
    outcome_unknown: bool = False


class PlatformResult(BaseModel):
    platform: PlatformName
    status: Literal["success", "failed", "simulated"]
    mode: Literal["real", "mock"]
    post_id: str | None = None
    posted_url: str | None = None
    url_source: Literal["api", "derived_from_id"] | None = None
    public_access: bool | None = None
    accessibility_verification: Literal["not_checked"] = "not_checked"
    date: str | None = None
    time: str | None = None
    timestamp_source: Literal["api_acknowledged_at"] | None = None
    error: ErrorDetail | None = None
    warnings: list[str] = Field(default_factory=list)


class PostingResponse(BaseModel):
    request_id: str
    mode: Literal["real", "mock"]
    success: bool
    success_count: int
    failure_count: int
    simulated_count: int
    total_count: int
    results: list[PlatformResult]
