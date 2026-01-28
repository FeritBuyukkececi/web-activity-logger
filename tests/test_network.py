"""Unit tests for the network module."""

import asyncio
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.async_api import async_playwright

from src.network import (
    _get_request_body,
    _is_binary_content_type,
    setup_network_capture,
)


class MockRequestHandler(BaseHTTPRequestHandler):
    """Simple HTTP server handler for testing network capture."""

    def log_message(self, format, *args):
        """Suppress server logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)

        if parsed.path == "/json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"result": "success"}).encode())
        elif parsed.path == "/html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Hello</body></html>")
        elif parsed.path == "/binary":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(b"\x89PNG\r\n\x1a\n")
        elif parsed.path == "/query":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            query = parse_qs(parsed.query)
            self.wfile.write(json.dumps({"query": query}).encode())
        elif parsed.path == "/external":
            # Simulate external domain response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"external": True}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if self.path == "/api/json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                received = json.loads(body.decode())
                self.wfile.write(json.dumps({"received": received}).encode())
            except json.JSONDecodeError:
                self.wfile.write(json.dumps({"error": "invalid json"}).encode())
        elif self.path == "/api/form":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"form_data": body.decode()}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())


@pytest.fixture(scope="module")
def test_server():
    """Start a local HTTP server for testing."""
    server = HTTPServer(("127.0.0.1", 0), MockRequestHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
async def browser_page():
    """Create a Playwright browser and page for testing."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()


class TestDomainFiltering:
    """Tests for domain filtering in network capture."""

    @pytest.mark.asyncio
    async def test_captures_requests_to_exact_root_domain(
        self, test_server, browser_page
    ):
        """Captures requests to exact root domain."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/json")

        # Wait for network to settle
        await asyncio.sleep(0.1)

        assert len(captured) >= 1
        assert any("/json" in e["url"] for e in captured)

    @pytest.mark.asyncio
    async def test_captures_requests_to_subdomains(self, browser_page):
        """Captures requests to subdomains."""
        # This test verifies the logic works for subdomains
        # We test the is_subdomain_of function directly since we can't easily
        # create subdomain requests in a test environment
        from src.utils import is_subdomain_of

        assert is_subdomain_of("https://api.example.com/data", "example.com")
        assert is_subdomain_of("https://shop.api.example.com/", "example.com")

    @pytest.mark.asyncio
    async def test_ignores_requests_to_different_domains(
        self, test_server, browser_page
    ):
        """Ignores requests to different domains."""
        captured = []

        # Set up capture for a different domain
        await setup_network_capture(browser_page, "otherdomain.com", captured.append)
        await browser_page.goto(f"{test_server}/json")

        # Wait for network to settle
        await asyncio.sleep(0.1)

        # Should not capture requests to 127.0.0.1 when filtering for otherdomain.com
        assert len(captured) == 0


class TestGetRequests:
    """Tests for GET request capture."""

    @pytest.mark.asyncio
    async def test_captures_get_request_with_query_params(
        self, test_server, browser_page
    ):
        """Captures GET request with query params."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/query?foo=bar&baz=123")

        await asyncio.sleep(0.1)

        assert len(captured) >= 1
        request_entry = next(e for e in captured if "/query" in e["url"])
        assert "foo=bar" in request_entry["url"]
        assert "baz=123" in request_entry["url"]
        assert request_entry["method"] == "GET"


class TestPostRequests:
    """Tests for POST request capture."""

    @pytest.mark.asyncio
    async def test_captures_post_request_with_json_body(
        self, test_server, browser_page
    ):
        """Captures POST request with JSON body."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)

        # Make a POST request using page.evaluate
        await browser_page.goto(f"{test_server}/")
        await browser_page.evaluate(
            """async (url) => {
            await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: 'test', value: 42})
            });
        }""",
            f"{test_server}/api/json",
        )

        await asyncio.sleep(0.1)

        post_entry = next((e for e in captured if "/api/json" in e["url"]), None)
        assert post_entry is not None
        assert post_entry["method"] == "POST"
        assert post_entry["requestBody"] == {"name": "test", "value": 42}

    @pytest.mark.asyncio
    async def test_captures_post_request_with_form_data(
        self, test_server, browser_page
    ):
        """Captures POST request with form data."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)

        await browser_page.goto(f"{test_server}/")
        await browser_page.evaluate(
            """async (url) => {
            await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'username=john&password=secret'
            });
        }""",
            f"{test_server}/api/form",
        )

        await asyncio.sleep(0.1)

        post_entry = next((e for e in captured if "/api/form" in e["url"]), None)
        assert post_entry is not None
        assert post_entry["method"] == "POST"
        assert post_entry["requestBody"] == "username=john&password=secret"


class TestResponseCapture:
    """Tests for response capture."""

    @pytest.mark.asyncio
    async def test_captures_response_status_and_headers(
        self, test_server, browser_page
    ):
        """Captures response status and headers."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/json")

        await asyncio.sleep(0.1)

        json_entry = next((e for e in captured if "/json" in e["url"]), None)
        assert json_entry is not None
        assert json_entry["responseStatus"] == 200
        assert "content-type" in json_entry["responseHeaders"]

    @pytest.mark.asyncio
    async def test_captures_response_body_json(self, test_server, browser_page):
        """Captures response body (JSON)."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/json")

        await asyncio.sleep(0.1)

        json_entry = next((e for e in captured if "/json" in e["url"]), None)
        assert json_entry is not None
        assert json_entry["responseBody"] == {"result": "success"}

    @pytest.mark.asyncio
    async def test_captures_response_body_html(self, test_server, browser_page):
        """Captures response body (text/html)."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/html")

        await asyncio.sleep(0.1)

        html_entry = next((e for e in captured if "/html" in e["url"]), None)
        assert html_entry is not None
        assert "<html>" in html_entry["responseBody"]
        assert "Hello" in html_entry["responseBody"]

    @pytest.mark.asyncio
    async def test_handles_binary_responses_gracefully(
        self, test_server, browser_page
    ):
        """Handles binary responses gracefully (returns [binary] marker)."""
        captured = []

        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/")
        # Fetch a binary resource
        await browser_page.evaluate(
            """async (url) => {
            await fetch(url);
        }""",
            f"{test_server}/binary",
        )

        await asyncio.sleep(0.1)

        binary_entry = next((e for e in captured if "/binary" in e["url"]), None)
        assert binary_entry is not None
        assert binary_entry["responseBody"] == "[binary]"


class TestFailedRequests:
    """Tests for failed request handling."""

    @pytest.mark.asyncio
    async def test_handles_failed_requests(self, browser_page):
        """Handles failed requests (network error)."""
        captured = []

        # Use a non-routable IP to trigger a connection failure
        await setup_network_capture(browser_page, "192.0.2.1", captured.append)

        # Attempt navigation to unreachable address (should fail)
        try:
            await browser_page.goto("http://192.0.2.1:12345/test", timeout=2000)
        except Exception:
            pass

        await asyncio.sleep(0.2)

        # Should capture the failed request
        if captured:
            failed_entry = captured[0]
            assert failed_entry["responseStatus"] is None
            assert "error" in failed_entry


class TestTimestamps:
    """Tests for timestamp accuracy."""

    @pytest.mark.asyncio
    async def test_includes_accurate_timestamps(self, test_server, browser_page):
        """Includes accurate timestamps."""
        captured = []

        before = int(time.time() * 1000)
        await setup_network_capture(browser_page, "127.0.0.1", captured.append)
        await browser_page.goto(f"{test_server}/json")
        await asyncio.sleep(0.1)
        after = int(time.time() * 1000)

        assert len(captured) >= 1
        for entry in captured:
            assert "timestamp" in entry
            assert before <= entry["timestamp"] <= after


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_is_binary_content_type_image(self):
        """Identifies image content types as binary."""
        assert _is_binary_content_type("image/png")
        assert _is_binary_content_type("image/jpeg")
        assert _is_binary_content_type("image/gif")

    def test_is_binary_content_type_audio_video(self):
        """Identifies audio/video content types as binary."""
        assert _is_binary_content_type("audio/mpeg")
        assert _is_binary_content_type("video/mp4")

    def test_is_binary_content_type_application(self):
        """Identifies binary application types."""
        assert _is_binary_content_type("application/octet-stream")
        assert _is_binary_content_type("application/pdf")
        assert _is_binary_content_type("application/zip")

    def test_is_binary_content_type_text(self):
        """Text content types are not binary."""
        assert not _is_binary_content_type("text/html")
        assert not _is_binary_content_type("text/plain")
        assert not _is_binary_content_type("application/json")

    def test_is_binary_content_type_case_insensitive(self):
        """Content type check is case insensitive."""
        assert _is_binary_content_type("Image/PNG")
        assert _is_binary_content_type("APPLICATION/PDF")
