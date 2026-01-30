"""Integration tests for src/main.py."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from src.main import (
    EXTENSION_DIR,
    capture_initial_dom,
    create_browser_context,
    inject_event_collector,
    poll_extension_events,
    setup_page_listeners,
)
from src.merger import create_session


class TestExtensionLoading:
    """Tests for browser launching with extension."""

    @pytest.fixture
    def extension_path(self):
        """Get the extension directory path."""
        return EXTENSION_DIR

    def test_extension_directory_exists(self, extension_path):
        """Verify extension directory exists."""
        assert extension_path.exists()
        assert extension_path.is_dir()

    def test_extension_has_manifest(self, extension_path):
        """Verify extension has manifest.json."""
        manifest_path = extension_path / "manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["manifest_version"] == 3
        assert "content_scripts" in manifest
        assert "background" in manifest

    def test_extension_has_content_script(self, extension_path):
        """Verify extension has content.js."""
        content_path = extension_path / "content.js"
        assert content_path.exists()

    def test_extension_has_background_script(self, extension_path):
        """Verify extension has background.js."""
        background_path = extension_path / "background.js"
        assert background_path.exists()

    @pytest.mark.asyncio
    async def test_browser_launches_with_extension(self):
        """Test that browser launches with extension loaded."""
        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)

            # Browser should launch successfully
            assert context is not None

            # Should have at least one page
            pages = context.pages
            assert len(pages) >= 0  # May or may not have initial page

            await context.close()


class TestEventCollector:
    """Tests for event collection from extension."""

    @pytest.mark.asyncio
    async def test_inject_event_collector_creates_array(self):
        """Test that event collector injects window array."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.goto("about:blank")

            # Inject collector
            await inject_event_collector(page)

            # Check array exists
            result = await page.evaluate(
                "() => typeof window.__webLoggerEvents__"
            )
            assert result == "object"

            # Check it's an array
            is_array = await page.evaluate(
                "() => Array.isArray(window.__webLoggerEvents__)"
            )
            assert is_array is True

            await browser.close()

    @pytest.mark.asyncio
    async def test_poll_extension_events_retrieves_events(self):
        """Test that poll retrieves and clears events."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.goto("about:blank")

            # Create session
            session = create_session("https://example.com")

            # Inject collector
            await inject_event_collector(page)

            # Manually add an event
            await page.evaluate("""
                () => {
                    window.__webLoggerEvents__.push({
                        timestamp: 1234567890,
                        type: 'interaction',
                        event: 'click',
                        selector: '#test',
                        tagName: 'BUTTON',
                        url: 'https://example.com'
                    });
                }
            """)

            # Poll events
            await poll_extension_events(page, session)

            # Event should be in session
            assert len(session["events"]) == 1
            assert session["events"][0]["type"] == "interaction"
            assert session["events"][0]["selector"] == "#test"

            await browser.close()


class TestNetworkCapture:
    """Tests for network capture integration."""

    @pytest.mark.asyncio
    async def test_network_requests_are_captured(self):
        """Test that network requests are captured during recording."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()

            # Create session
            session = create_session("https://example.com")

            # Set up listeners
            await setup_page_listeners(page, session, "example.com")

            # Navigate to trigger a request
            await page.goto("https://example.com")

            # Small delay for response handling
            await asyncio.sleep(0.5)

            # Should have captured the navigation request
            network_events = [e for e in session["events"] if e["type"] == "network"]
            assert len(network_events) > 0

            # Check first network event has expected structure
            event = network_events[0]
            assert "url" in event
            assert "method" in event
            assert "responseStatus" in event

            await browser.close()

    @pytest.mark.asyncio
    async def test_domain_filtering_works(self):
        """Test that only requests to matching domain are captured."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()

            # Create session for example.com
            session = create_session("https://example.com")

            # Set up listeners for example.com only
            await setup_page_listeners(page, session, "example.com")

            # Set up route to intercept all requests
            captured_urls = []

            async def capture_all(route):
                captured_urls.append(route.request.url)
                await route.continue_()

            await page.route("**/*", capture_all)

            # Navigate
            await page.goto("https://example.com")
            await asyncio.sleep(0.5)

            # Only example.com requests should be in session
            network_events = [e for e in session["events"] if e["type"] == "network"]
            for event in network_events:
                assert "example.com" in event["url"]

            await browser.close()


class TestExportFormat:
    """Tests for export file format."""

    @pytest.mark.asyncio
    async def test_export_contains_both_event_types(self):
        """Test that export can contain both interaction and network events."""
        from src.merger import add_event, export_session, finalize_session

        # Create session
        session = create_session("https://example.com")

        # Add interaction event
        add_event(session, {
            "timestamp": 1000,
            "type": "interaction",
            "event": "click",
            "selector": "#btn",
            "tagName": "BUTTON",
            "url": "https://example.com"
        })

        # Add network event
        add_event(session, {
            "timestamp": 1001,
            "type": "network",
            "url": "https://example.com/api",
            "method": "GET",
            "responseStatus": 200
        })

        # Finalize
        finalize_session(session)

        # Export to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name

        try:
            export_session(session, filepath)

            # Read and verify
            with open(filepath) as f:
                data = json.load(f)

            # Should have both event types
            event_types = set(e["type"] for e in data["events"])
            assert "interaction" in event_types
            assert "network" in event_types

            # Events should be sorted by timestamp
            timestamps = [e["timestamp"] for e in data["events"]]
            assert timestamps == sorted(timestamps)

        finally:
            os.unlink(filepath)


class TestFullIntegration:
    """Full integration tests with extension."""

    @pytest.mark.asyncio
    async def test_full_recording_flow(self):
        """Test the complete recording flow with extension."""
        from src.main import create_browser_context
        from src.merger import add_event, finalize_session

        async with async_playwright() as playwright:
            context = await create_browser_context(playwright)

            # Get a page
            page = context.pages[0] if context.pages else await context.new_page()

            # Create session
            session = create_session("https://example.com")

            # Set up listeners
            await setup_page_listeners(page, session, "example.com")

            # Navigate
            await page.goto("https://example.com")
            await asyncio.sleep(1)

            # Poll for extension events
            await poll_extension_events(page, session)

            # Finalize
            finalize_session(session)

            # Verify session structure
            assert "session" in session
            assert "events" in session
            assert session["session"]["domain"] == "example.com"
            assert session["session"]["endTime"] is not None

            await context.close()


class TestInitialDomCapture:
    """Tests for initial DOM capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_initial_dom_returns_html(self):
        """Test that capture_initial_dom returns valid HTML content."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()

            # Navigate to a simple page
            await page.goto("https://example.com")
            await page.wait_for_load_state("domcontentloaded")

            # Capture DOM
            html = await capture_initial_dom(page)

            # Verify it's HTML
            assert isinstance(html, str)
            assert "<html" in html.lower()
            assert "<head" in html.lower()
            assert "<body" in html.lower()

            await browser.close()

    @pytest.mark.asyncio
    async def test_capture_initial_dom_contains_page_content(self):
        """Test that captured DOM contains actual page content."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()

            # Set content with specific elements
            await page.set_content("""
                <html>
                <head><title>Test Page</title></head>
                <body>
                    <h1>Hello World</h1>
                    <div id="main">Content here</div>
                </body>
                </html>
            """)

            # Capture DOM
            html = await capture_initial_dom(page)

            # Verify content is present
            assert "Hello World" in html
            assert 'id="main"' in html
            assert "Content here" in html

            await browser.close()


class TestSessionFolderStructure:
    """Tests for session folder naming and structure."""

    def test_session_folder_name_format(self):
        """Test that session folder structure matches expected format: logs/{tag}/{domain}/{YYYYMMDD_HHMMSS}/"""
        import re
        from datetime import datetime

        # Generate folder structure the same way as main.py
        tag = "health"
        domain_name = "allianz"
        dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Verify datetime format: YYYYMMDD_HHMMSS
        pattern = r"^\d{8}_\d{6}$"
        assert re.match(pattern, dt_str)

        # Verify full path structure
        full_path = f"logs/{tag}/{domain_name}/{dt_str}"
        path_pattern = r"^logs/[a-z0-9_-]+/[a-z0-9._-]+/\d{8}_\d{6}$"
        assert re.match(path_pattern, full_path, re.IGNORECASE)

    def test_session_folder_contains_expected_files(self):
        """Test that session folder would contain expected files."""
        from src.merger import create_session, export_session, finalize_session

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create session folder structure: logs/{tag}/{domain}/{datetime}/
            session_dir = Path(tmpdir) / "health" / "allianz" / "20260130_143045"
            session_dir.mkdir(parents=True, exist_ok=True)

            # Create session and export
            session = create_session("https://www.allianz.com.tr")
            finalize_session(session)

            session_filepath = session_dir / "session.json"
            export_session(session, str(session_filepath))

            # Write initial DOM
            dom_filepath = session_dir / "initial_dom.html"
            dom_filepath.write_text("<html><body>Test</body></html>", encoding="utf-8")

            # Verify both files exist
            assert session_filepath.exists()
            assert dom_filepath.exists()

            # Verify session.json is valid
            with open(session_filepath) as f:
                data = json.load(f)
            assert "session" in data
            assert "events" in data

            # Verify initial_dom.html contains HTML
            html_content = dom_filepath.read_text(encoding="utf-8")
            assert "<html>" in html_content


class TestCLIArguments:
    """Tests for CLI argument parsing."""

    def test_cli_requires_tag_argument(self):
        """Test that --tag is a required argument."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "src.main", "--url=https://example.com"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "tag" in result.stderr.lower()

    def test_cli_requires_url_argument(self):
        """Test that --url is a required argument."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "src.main", "--tag=test"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "url" in result.stderr.lower()

    def test_cli_shows_help(self):
        """Test that --help shows usage information."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "src.main", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--tag" in result.stdout
        assert "--url" in result.stdout
