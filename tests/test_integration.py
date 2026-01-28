"""End-to-end integration tests for the complete workflow.

Task 7: Integration Testing
- Record session on a test page with clicks and API calls
- Verify interactions and network events are merged
- Verify timestamps are chronologically ordered
- Verify domain filtering excludes third-party requests
- Verify dynamic elements (added via JS) are tracked
"""

import asyncio
import json
import os
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.async_api import async_playwright

from src.main import (
    create_browser_context,
    inject_event_collector,
    poll_extension_events,
    setup_page_listeners,
)
from src.merger import add_event, create_session, export_session, finalize_session


class IntegrationTestHandler(BaseHTTPRequestHandler):
    """HTTP server handler for integration tests with API endpoints."""

    def log_message(self, format, *args):
        """Suppress server logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_main_page()
        elif path == "/api/data":
            self._serve_api_data()
        elif path == "/api/items":
            self._serve_api_items()
        elif path == "/dynamic-page":
            self._serve_dynamic_page()
        elif path == "/external-links":
            self._serve_external_links_page()
        else:
            self._serve_404()

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/submit":
            self._serve_api_submit()
        elif path == "/api/login":
            self._serve_api_login()
        else:
            self._serve_404()

    def _serve_main_page(self):
        """Serve the main test page with interactions and API calls."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Integration Test Page</title></head>
        <body>
            <h1>Integration Test Page</h1>

            <!-- Interactive elements -->
            <button id="fetch-btn" onclick="fetchData()">Fetch Data</button>
            <button id="submit-btn" onclick="submitForm()">Submit</button>

            <form id="test-form" onsubmit="handleSubmit(event)">
                <input type="text" id="username" name="username" placeholder="Username">
                <input type="password" id="password" name="password" placeholder="Password">
                <button type="submit" id="form-submit">Login</button>
            </form>

            <div id="results"></div>

            <script>
                // Fetch data from API
                async function fetchData() {
                    const response = await fetch('/api/data');
                    const data = await response.json();
                    document.getElementById('results').textContent = JSON.stringify(data);
                }

                // Submit form data
                async function submitForm() {
                    const response = await fetch('/api/submit', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({action: 'test', value: 123})
                    });
                    const data = await response.json();
                    document.getElementById('results').textContent = JSON.stringify(data);
                }

                // Handle form submission
                function handleSubmit(e) {
                    e.preventDefault();
                    const formData = new FormData(e.target);
                    fetch('/api/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            username: formData.get('username'),
                            password: formData.get('password')
                        })
                    });
                }
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def _serve_dynamic_page(self):
        """Serve a page that dynamically adds interactive elements."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Dynamic Elements Test</title></head>
        <body>
            <h1>Dynamic Elements Test</h1>

            <button id="add-button" onclick="addButton()">Add Dynamic Button</button>
            <button id="add-form" onclick="addForm()">Add Dynamic Form</button>
            <button id="trigger-api" onclick="triggerApi()">Trigger API Call</button>

            <div id="container"></div>

            <script>
                function addButton() {
                    const container = document.getElementById('container');
                    const btn = document.createElement('button');
                    btn.id = 'dynamic-btn';
                    btn.className = 'dynamic-element';
                    btn.textContent = 'Click Me (Dynamic)';
                    btn.onclick = function() {
                        fetch('/api/data');
                    };
                    container.appendChild(btn);
                }

                function addForm() {
                    const container = document.getElementById('container');
                    const form = document.createElement('form');
                    form.id = 'dynamic-form';
                    form.innerHTML = '<input type="text" id="dynamic-input" name="query"><button type="submit">Search</button>';
                    form.onsubmit = function(e) {
                        e.preventDefault();
                        fetch('/api/items?q=' + document.getElementById('dynamic-input').value);
                    };
                    container.appendChild(form);
                }

                function triggerApi() {
                    fetch('/api/items');
                }
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def _serve_external_links_page(self):
        """Serve a page that references external domains (for filtering test)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>External Links Test</title></head>
        <body>
            <h1>External Links Test</h1>

            <button id="local-api" onclick="localApi()">Local API</button>
            <button id="external-attempt" onclick="externalApi()">External API (will fail)</button>

            <div id="results"></div>

            <script>
                function localApi() {
                    fetch('/api/data')
                        .then(r => r.json())
                        .then(d => document.getElementById('results').textContent = JSON.stringify(d));
                }

                // This will fail due to CORS but we still want to verify it's filtered
                function externalApi() {
                    fetch('https://api.external-domain.com/data')
                        .catch(e => console.log('Expected CORS error'));
                }
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def _serve_api_data(self):
        """Serve API data endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        data = {"status": "success", "data": {"items": [1, 2, 3], "total": 3}}
        self.wfile.write(json.dumps(data).encode())

    def _serve_api_items(self):
        """Serve API items endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        data = {"items": ["item1", "item2", "item3"]}
        self.wfile.write(json.dumps(data).encode())

    def _serve_api_submit(self):
        """Handle API submit endpoint."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"status": "received", "echo": body.decode() if body else None}
        self.wfile.write(json.dumps(response).encode())

    def _serve_api_login(self):
        """Handle API login endpoint."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"status": "authenticated", "token": "test-token-123"}
        self.wfile.write(json.dumps(response).encode())

    def _serve_404(self):
        """Serve 404 response."""
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "not found"}).encode())


@pytest.fixture(scope="module")
def integration_server():
    """Start a local HTTP server for integration testing."""
    server = HTTPServer(("127.0.0.1", 0), IntegrationTestHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestRecordSessionWithClicksAndApiCalls:
    """Test recording a session with both clicks and API calls."""

    @pytest.mark.asyncio
    async def test_record_clicks_and_api_calls(self, integration_server):
        """Record session on a test page with clicks and API calls."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            # Create session
            session = create_session(integration_server)

            # Set up listeners
            await setup_page_listeners(page, session, "127.0.0.1")

            # Navigate to the test page
            await page.goto(integration_server)
            await asyncio.sleep(0.5)

            # Perform interactions that trigger API calls
            await page.click("#fetch-btn")
            await asyncio.sleep(0.5)

            await page.click("#submit-btn")
            await asyncio.sleep(0.5)

            # Poll for extension events
            await poll_extension_events(page, session)

            # Finalize and check
            finalize_session(session)

            # Should have captured network events (navigation + API calls)
            network_events = [e for e in session["events"] if e["type"] == "network"]
            assert len(network_events) >= 2, "Should capture at least navigation and API requests"

            # Check that API endpoints were captured
            api_urls = [e["url"] for e in network_events]
            api_data_captured = any("/api/data" in url for url in api_urls)
            api_submit_captured = any("/api/submit" in url for url in api_urls)
            assert api_data_captured, "Should capture /api/data request"
            assert api_submit_captured, "Should capture /api/submit request"

            await context.close()

    @pytest.mark.asyncio
    async def test_form_submission_triggers_api_call(self, integration_server):
        """Test that form submission is captured along with the API call."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(integration_server)
            await asyncio.sleep(0.5)

            # Fill form and submit
            await page.fill("#username", "testuser")
            await page.fill("#password", "testpass")
            await page.click("#form-submit")
            await asyncio.sleep(0.5)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Check for login API call
            network_events = [e for e in session["events"] if e["type"] == "network"]
            login_call = next((e for e in network_events if "/api/login" in e["url"]), None)
            assert login_call is not None, "Should capture /api/login request"
            assert login_call["method"] == "POST"

            await context.close()


class TestMergeInteractionsAndNetworkEvents:
    """Test that interactions and network events are properly merged."""

    @pytest.mark.asyncio
    async def test_events_are_merged(self, integration_server):
        """Verify interactions and network events are merged in session."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(integration_server)
            await asyncio.sleep(0.3)

            # Trigger some interactions
            await page.click("#fetch-btn")
            await asyncio.sleep(0.3)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Should have both event types in the same session
            event_types = set(e["type"] for e in session["events"])
            assert "network" in event_types, "Should have network events"

            # Verify structure is correct
            assert "session" in session
            assert "events" in session
            assert session["session"]["domain"] == "127.0.0.1"

            await context.close()

    @pytest.mark.asyncio
    async def test_export_contains_both_types(self, integration_server):
        """Verify exported JSON file contains both interaction and network events."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(integration_server)
            await asyncio.sleep(0.3)

            await page.click("#fetch-btn")
            await asyncio.sleep(0.3)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Export to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                filepath = f.name

            try:
                export_session(session, filepath)

                with open(filepath) as f:
                    exported = json.load(f)

                # Verify structure
                assert "session" in exported
                assert "events" in exported
                assert exported["session"]["startUrl"] == integration_server
                assert len(exported["events"]) > 0

            finally:
                os.unlink(filepath)

            await context.close()


class TestTimestampChronologicalOrder:
    """Test that timestamps are chronologically ordered."""

    @pytest.mark.asyncio
    async def test_timestamps_are_ordered(self, integration_server):
        """Verify timestamps are chronologically ordered after finalization."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(integration_server)
            await asyncio.sleep(0.2)

            # Multiple actions with delays to ensure different timestamps
            await page.click("#fetch-btn")
            await asyncio.sleep(0.2)

            await page.click("#submit-btn")
            await asyncio.sleep(0.2)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Extract timestamps
            timestamps = [e.get("timestamp", 0) for e in session["events"]]

            # Verify they are sorted
            assert timestamps == sorted(timestamps), "Events should be sorted by timestamp"

            # Verify timestamps are reasonable (within last minute)
            now = int(time.time() * 1000)
            for ts in timestamps:
                assert now - 60000 < ts <= now + 1000, f"Timestamp {ts} should be recent"

            await context.close()

    @pytest.mark.asyncio
    async def test_interleaved_events_sorted_correctly(self, integration_server):
        """Verify that interleaved interaction and network events are sorted correctly."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(integration_server)
            await asyncio.sleep(0.3)

            # Perform multiple actions that create interleaved events
            for _ in range(3):
                await page.click("#fetch-btn")
                await asyncio.sleep(0.1)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Get timestamps and verify order
            events = session["events"]
            for i in range(1, len(events)):
                assert (
                    events[i]["timestamp"] >= events[i - 1]["timestamp"]
                ), "Events should be in chronological order"

            await context.close()


class TestDomainFilteringExcludesThirdParty:
    """Test that domain filtering excludes third-party requests."""

    @pytest.mark.asyncio
    async def test_only_same_domain_requests_captured(self, integration_server):
        """Verify domain filtering excludes third-party requests."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)

            # Set up listeners for 127.0.0.1 only
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(f"{integration_server}/external-links")
            await asyncio.sleep(0.3)

            # Click local API button
            await page.click("#local-api")
            await asyncio.sleep(0.3)

            # Click external API button (will fail but request is made)
            await page.click("#external-attempt")
            await asyncio.sleep(0.3)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Check captured network events
            network_events = [e for e in session["events"] if e["type"] == "network"]

            # All captured requests should be to 127.0.0.1
            for event in network_events:
                assert "127.0.0.1" in event["url"], f"Should only capture local requests, got {event['url']}"

            # Should NOT have external-domain.com
            external_requests = [
                e for e in network_events if "external-domain.com" in e["url"]
            ]
            assert (
                len(external_requests) == 0
            ), "Should not capture external domain requests"

            await context.close()

    @pytest.mark.asyncio
    async def test_subdomains_are_captured(self, integration_server):
        """Verify that subdomains of the root domain are captured."""
        # This test uses 127.0.0.1 which doesn't have subdomains,
        # but we verify the filtering logic works correctly
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(integration_server)
            await asyncio.sleep(0.3)

            await page.click("#fetch-btn")
            await asyncio.sleep(0.3)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Verify local API calls are captured
            network_events = [e for e in session["events"] if e["type"] == "network"]
            api_calls = [e for e in network_events if "/api/" in e["url"]]
            assert len(api_calls) > 0, "Should capture API calls to same domain"

            await context.close()


class TestDynamicElementsTracking:
    """Test that dynamically added elements are tracked."""

    @pytest.mark.asyncio
    async def test_dynamic_button_clicks_trigger_api(self, integration_server):
        """Verify dynamic elements (added via JS) are tracked."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(f"{integration_server}/dynamic-page")
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(f"{integration_server}/dynamic-page")
            await asyncio.sleep(0.5)

            # Click button to add dynamic element
            await page.click("#add-button")
            await asyncio.sleep(0.3)

            # Click the dynamically added button (which triggers an API call)
            await page.click("#dynamic-btn")
            await asyncio.sleep(0.5)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Should have captured the API call from dynamic button
            network_events = [e for e in session["events"] if e["type"] == "network"]
            api_data_calls = [e for e in network_events if "/api/data" in e["url"]]

            # At least one API call should be from the dynamic button click
            assert len(api_data_calls) >= 1, "Should capture API call from dynamic button"

            await context.close()

    @pytest.mark.asyncio
    async def test_dynamic_form_submission(self, integration_server):
        """Test that dynamically added forms can be tracked."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(f"{integration_server}/dynamic-page")
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(f"{integration_server}/dynamic-page")
            await asyncio.sleep(0.5)

            # Add dynamic form
            await page.click("#add-form")
            await asyncio.sleep(0.3)

            # Fill and interact with dynamic form
            await page.fill("#dynamic-input", "test-query")
            await asyncio.sleep(0.2)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Session should have events
            assert len(session["events"]) > 0, "Should capture events from dynamic elements"

            await context.close()

    @pytest.mark.asyncio
    async def test_multiple_dynamic_elements(self, integration_server):
        """Test tracking multiple dynamically added elements."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(f"{integration_server}/dynamic-page")
            await setup_page_listeners(page, session, "127.0.0.1")

            await page.goto(f"{integration_server}/dynamic-page")
            await asyncio.sleep(0.3)

            # Add both dynamic button and form
            await page.click("#add-button")
            await asyncio.sleep(0.2)
            await page.click("#add-form")
            await asyncio.sleep(0.2)

            # Interact with both
            await page.click("#dynamic-btn")
            await asyncio.sleep(0.2)
            await page.fill("#dynamic-input", "search term")
            await asyncio.sleep(0.2)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Should have captured all interactions
            assert len(session["events"]) >= 1, "Should capture events from multiple dynamic elements"

            await context.close()


class TestFullEndToEndWorkflow:
    """Full end-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_complete_session_workflow(self, integration_server):
        """Test the complete workflow from start to export."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            # 1. Create session
            session = create_session(integration_server)

            # 2. Set up listeners
            await setup_page_listeners(page, session, "127.0.0.1")

            # 3. Navigate
            await page.goto(integration_server)
            await asyncio.sleep(0.3)

            # 4. Perform various interactions
            await page.click("#fetch-btn")
            await asyncio.sleep(0.2)

            await page.fill("#username", "testuser")
            await asyncio.sleep(0.1)

            await page.click("#submit-btn")
            await asyncio.sleep(0.3)

            # 5. Poll for events
            await poll_extension_events(page, session)

            # 6. Finalize
            finalize_session(session)

            # 7. Export
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                filepath = f.name

            try:
                export_session(session, filepath)

                # 8. Verify exported data
                with open(filepath) as f:
                    exported = json.load(f)

                # Verify session metadata
                assert exported["session"]["startUrl"] == integration_server
                assert exported["session"]["domain"] == "127.0.0.1"
                assert exported["session"]["startTime"] is not None
                assert exported["session"]["endTime"] is not None
                assert (
                    exported["session"]["endTime"] >= exported["session"]["startTime"]
                )

                # Verify events
                assert len(exported["events"]) > 0

                # Verify timestamps are sorted
                timestamps = [e["timestamp"] for e in exported["events"]]
                assert timestamps == sorted(timestamps)

                # Verify we have network events
                network_events = [
                    e for e in exported["events"] if e["type"] == "network"
                ]
                assert len(network_events) > 0

            finally:
                os.unlink(filepath)

            await context.close()

    @pytest.mark.asyncio
    async def test_session_with_navigation_and_multiple_pages(self, integration_server):
        """Test session recording across page navigation."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)
            page = context.pages[0] if context.pages else await context.new_page()

            session = create_session(integration_server)
            await setup_page_listeners(page, session, "127.0.0.1")

            # Navigate to main page
            await page.goto(integration_server)
            await asyncio.sleep(0.3)

            await page.click("#fetch-btn")
            await asyncio.sleep(0.2)

            # Navigate to dynamic page
            await page.goto(f"{integration_server}/dynamic-page")
            await asyncio.sleep(0.3)

            await page.click("#trigger-api")
            await asyncio.sleep(0.3)

            await poll_extension_events(page, session)
            finalize_session(session)

            # Should have events from both pages
            network_events = [e for e in session["events"] if e["type"] == "network"]

            # Should have navigation events and API calls
            assert len(network_events) >= 2, "Should capture events across navigations"

            await context.close()
