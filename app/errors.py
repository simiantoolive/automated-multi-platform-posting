"""Sanitized error mapping. Never return upstream bodies, request URLs or tokens."""
import asyncio
import httpx
from app.schemas import ErrorDetail


class PlatformError(Exception):
    def __init__(self, code: str, message: str, *, outcome_unknown: bool = False):
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.outcome_unknown = outcome_unknown


def error_detail(exc: Exception) -> ErrorDetail:
    if isinstance(exc, PlatformError):
        return ErrorDetail(code=exc.code, message=exc.safe_message, outcome_unknown=exc.outcome_unknown)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        code, message = "api_error", "Platform rejected the request."
        if status == 401:
            code, message = "authentication_failed", "Invalid or expired access token."
        elif status == 403:
            code, message = "permission_denied", "Check posting permissions, account roles and app approval."
        elif status == 429:
            code, message = "rate_limited", "Platform rate limit reached; wait before retrying."
        elif status == 402:
            code, message = "access_payment_required", "Check platform API entitlement and available credits."
        elif status >= 500:
            code, message = "upstream_unavailable", "Platform failed; check for an existing post before retrying."
        retry = exc.response.headers.get("retry-after", "")
        seconds = int(retry) if retry.isdigit() and len(retry) <= 8 else None
        return ErrorDetail(code=code, message=message, http_status=status,
                           retry_after_seconds=seconds, outcome_unknown=status >= 500)
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return ErrorDetail(code="timeout", message="Request timed out; check the platform before retrying.",
                           outcome_unknown=True)
    if isinstance(exc, httpx.RequestError):
        return ErrorDetail(code="network_error", message="Network request failed; check the platform before retrying.",
                           outcome_unknown=True)
    return ErrorDetail(code="unexpected_response",
                       message="Unexpected platform response; check the platform before retrying.",
                       outcome_unknown=True)
