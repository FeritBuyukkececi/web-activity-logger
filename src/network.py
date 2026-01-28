"""Playwright network interception with domain filtering and request/response capture."""

import json
import time
from typing import Callable

from playwright.async_api import Page, Request, Response

from .utils import is_subdomain_of


async def setup_network_capture(
    page: Page, root_domain: str, on_request: Callable[[dict], None]
) -> None:
    """
    Set up network interception on a Playwright page.

    Intercepts all requests, filters to root_domain + subdomains,
    captures full request/response bodies, and calls on_request callback.

    Args:
        page: Playwright Page object to attach listeners to.
        root_domain: The root domain to filter requests (e.g., "example.com").
        on_request: Callback function that receives network log entries.
    """

    async def handle_response(response: Response) -> None:
        """Handle a completed response."""
        request = response.request
        url = request.url

        # Filter to root domain and subdomains only
        if not is_subdomain_of(url, root_domain):
            return

        timestamp = int(time.time() * 1000)

        # Build request body
        request_body = _get_request_body(request)

        # Build response body
        response_body = await _get_response_body(response)

        # Build the network log entry
        entry = {
            "timestamp": timestamp,
            "type": "network",
            "url": url,
            "method": request.method,
            "requestHeaders": dict(request.headers),
            "requestBody": request_body,
            "responseStatus": response.status,
            "responseHeaders": dict(response.headers),
            "responseBody": response_body,
        }

        on_request(entry)

    async def handle_request_failed(request: Request) -> None:
        """Handle a failed request (network error)."""
        url = request.url

        # Filter to root domain and subdomains only
        if not is_subdomain_of(url, root_domain):
            return

        timestamp = int(time.time() * 1000)
        request_body = _get_request_body(request)

        # Build the network log entry for failed request
        entry = {
            "timestamp": timestamp,
            "type": "network",
            "url": url,
            "method": request.method,
            "requestHeaders": dict(request.headers),
            "requestBody": request_body,
            "responseStatus": None,
            "responseHeaders": {},
            "responseBody": None,
            "error": request.failure,
        }

        on_request(entry)

    # Attach event listeners
    page.on("response", handle_response)
    page.on("requestfailed", handle_request_failed)


def _get_request_body(request: Request) -> str | dict | None:
    """
    Extract the request body, parsing JSON if applicable.

    Returns:
        Parsed JSON dict, raw string, or None if no body.
    """
    post_data = request.post_data
    if post_data is None:
        return None

    # Try to parse as JSON
    try:
        return json.loads(post_data)
    except (json.JSONDecodeError, TypeError):
        return post_data


async def _get_response_body(response: Response) -> str | dict | None:
    """
    Extract the response body, handling different content types.

    Returns:
        Parsed JSON dict, text string, "[binary]" for binary content, or None on error.
    """
    try:
        content_type = response.headers.get("content-type", "")

        # Check if it's a binary content type
        if _is_binary_content_type(content_type):
            return "[binary]"

        # Try to get text body
        body = await response.text()

        # Try to parse as JSON if content type suggests it
        if "application/json" in content_type or body.startswith(("{", "[")):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass

        return body

    except Exception:
        # Response body might not be available (e.g., redirects, certain error responses)
        return None


def _is_binary_content_type(content_type: str) -> bool:
    """Check if content type indicates binary data."""
    binary_types = [
        "image/",
        "audio/",
        "video/",
        "application/octet-stream",
        "application/pdf",
        "application/zip",
        "application/gzip",
        "font/",
        "application/font",
        "application/x-font",
    ]
    return any(bt in content_type.lower() for bt in binary_types)
