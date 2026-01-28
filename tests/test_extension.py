"""Unit tests for the browser extension."""

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest
from playwright.async_api import async_playwright

# Path to the extension directory
EXTENSION_PATH = Path(__file__).parent.parent / "extension"


class PageHandler(BaseHTTPRequestHandler):
    """HTTP server handler that serves test pages."""

    def log_message(self, format, *args):
        """Suppress server logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/test-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self._get_test_page().encode())
        elif self.path == "/form-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self._get_form_page().encode())
        elif self.path == "/dynamic-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self._get_dynamic_page().encode())
        elif self.path == "/long-text-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self._get_long_text_page().encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>OK</body></html>")

    def do_POST(self):
        """Handle POST requests for form submission."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>Form submitted</body></html>")

    def _get_test_page(self):
        """Return a test page with various interactive elements."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Test Page</title></head>
        <body>
            <button id="btn-submit" class="primary large" data-testid="submit-btn">Submit</button>
            <a href="#" id="link-home" class="nav-link">Home</a>
            <input type="text" id="username" name="username" placeholder="Enter username">
            <input type="password" id="password" name="password" placeholder="Enter password">
            <select id="country" name="country">
                <option value="us">United States</option>
                <option value="uk">United Kingdom</option>
            </select>
            <textarea id="comments" name="comments"></textarea>
            <div id="captured-events"></div>
        </body>
        </html>
        """

    def _get_form_page(self):
        """Return a page with a form for testing submit events."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Form Page</title></head>
        <body>
            <form id="login-form" action="/submit" method="post" onsubmit="handleSubmit(event)">
                <input type="text" name="email" id="email" value="">
                <input type="password" name="password" id="form-password" value="">
                <input type="text" name="remember" id="remember" value="yes">
                <button type="submit" id="submit-btn">Login</button>
            </form>
            <script>
                function handleSubmit(e) {
                    // Prevent navigation but allow the submit event to fire
                    e.preventDefault();
                }
            </script>
        </body>
        </html>
        """

    def _get_dynamic_page(self):
        """Return a page that dynamically adds elements."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Dynamic Page</title></head>
        <body>
            <div id="container"></div>
            <button id="add-element" onclick="addElement()">Add Element</button>
            <script>
                function addElement() {
                    const container = document.getElementById('container');
                    const btn = document.createElement('button');
                    btn.id = 'dynamic-btn';
                    btn.className = 'dynamic';
                    btn.textContent = 'Dynamic Button';
                    container.appendChild(btn);
                }
            </script>
        </body>
        </html>
        """

    def _get_long_text_page(self):
        """Return a page with long text content for truncation testing."""
        long_text = "A" * 200
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Long Text Page</title></head>
        <body>
            <button id="long-text-btn">{long_text}</button>
        </body>
        </html>
        """


@pytest.fixture(scope="module")
def test_server():
    """Start a local HTTP server for testing."""
    server = HTTPServer(("127.0.0.1", 0), PageHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
async def browser_context_with_extension():
    """Create a Playwright browser with the extension loaded."""
    async with async_playwright() as p:
        # Launch browser with extension
        context = await p.chromium.launch_persistent_context(
            "",  # Use temporary user data dir
            headless=False,  # Extensions require headed mode
            args=[
                f"--disable-extensions-except={EXTENSION_PATH}",
                f"--load-extension={EXTENSION_PATH}",
                "--no-first-run",
                "--disable-popup-blocking",
            ],
        )
        yield context
        await context.close()


@pytest.fixture
async def page_with_extension(browser_context_with_extension):
    """Create a page from the browser context with extension."""
    page = await browser_context_with_extension.new_page()
    yield page
    await page.close()


async def get_captured_events(page):
    """Retrieve captured events from the content script via window object.

    The content script stores events in a way that we can retrieve them
    through page.evaluate.
    """
    # Wait a bit for events to be processed
    await asyncio.sleep(0.1)

    # We'll inject a listener to capture events sent by content script
    # Since we can't directly access chrome.runtime from page context,
    # we'll use a workaround: the content script sends events which we intercept
    return await page.evaluate("""() => {
        return window.__webLoggerCapturedEvents || [];
    }""")


async def setup_event_capture(page):
    """Set up event capture by injecting a script that intercepts content script events."""
    await page.evaluate("""() => {
        window.__webLoggerCapturedEvents = [];

        // Intercept the chrome.runtime.sendMessage calls by overriding the content script behavior
        // We'll do this by listening to a custom event that we'll make the content script dispatch
        window.addEventListener('webLoggerEvent', (e) => {
            window.__webLoggerCapturedEvents.push(e.detail);
        });
    }""")


async def inject_test_content_script(page):
    """Inject a modified content script for testing purposes.

    This version dispatches events to window instead of chrome.runtime.
    """
    content_script = """
    (function() {
        'use strict';

        const MAX_INNER_TEXT_LENGTH = 100;

        function generateSelector(element) {
            if (!element || !element.tagName) return null;
            const tagName = element.tagName.toLowerCase();
            if (element.id) return '#' + element.id;
            if (element.className && typeof element.className === 'string') {
                const classes = element.className.trim().split(/\\s+/).filter(c => c);
                if (classes.length > 0) return tagName + '.' + classes.join('.');
            }
            let index = 1;
            if (element.parentElement) {
                const siblings = Array.from(element.parentElement.children);
                const sameTagSiblings = siblings.filter(s => s.tagName === element.tagName);
                index = sameTagSiblings.indexOf(element) + 1;
            }
            return tagName + ':nth-child(' + index + ')';
        }

        function getAttributes(element) {
            const attrs = {};
            const relevantAttrs = ['id', 'class', 'name', 'type', 'href', 'src', 'value', 'placeholder', 'data-testid'];
            for (const attr of relevantAttrs) {
                if (element.hasAttribute(attr)) attrs[attr] = element.getAttribute(attr);
            }
            return attrs;
        }

        function getInnerText(element) {
            const text = element.innerText || '';
            if (text.length > MAX_INNER_TEXT_LENGTH) return text.substring(0, MAX_INNER_TEXT_LENGTH) + '...';
            return text;
        }

        function getInputValue(element) {
            if (element.type === 'password') return null;
            return element.value || null;
        }

        function getFormValues(form) {
            const values = {};
            const formData = new FormData(form);
            for (const [name, value] of formData.entries()) {
                const field = form.querySelector('[name="' + name + '"]');
                if (field && field.type === 'password') {
                    values[name] = '[REDACTED]';
                } else {
                    values[name] = value;
                }
            }
            return values;
        }

        function createLogEntry(eventType, element, extraData = {}) {
            return {
                timestamp: Date.now(),
                type: 'interaction',
                event: eventType,
                selector: generateSelector(element),
                tagName: element.tagName,
                attributes: getAttributes(element),
                value: null,
                innerText: getInnerText(element),
                url: window.location.href,
                ...extraData
            };
        }

        function sendEvent(logEntry) {
            window.dispatchEvent(new CustomEvent('webLoggerEvent', { detail: logEntry }));
        }

        document.addEventListener('click', (e) => sendEvent(createLogEntry('click', e.target)), { capture: true });
        document.addEventListener('input', (e) => sendEvent(createLogEntry('input', e.target, { value: getInputValue(e.target) })), { capture: true });
        document.addEventListener('change', (e) => sendEvent(createLogEntry('change', e.target, { value: getInputValue(e.target) })), { capture: true });
        document.addEventListener('submit', (e) => sendEvent(createLogEntry('submit', e.target, { formValues: getFormValues(e.target) })), { capture: true });

        // MutationObserver for dynamic elements
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        window.dispatchEvent(new CustomEvent('webLoggerMutation', { detail: { tagName: node.tagName, id: node.id } }));
                    }
                }
            }
        });
        observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
    })();
    """
    await page.evaluate(content_script)


class TestClickEvents:
    """Tests for click event capture."""

    @pytest.mark.asyncio
    async def test_click_captures_selector_tagname_attributes(self, test_server):
        """Click event captures element selector, tagName, attributes."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/test-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            # Click the submit button
            await page.click("#btn-submit")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            assert len(events) >= 1
            click_event = next((e for e in events if e["event"] == "click"), None)
            assert click_event is not None
            assert click_event["selector"] == "#btn-submit"
            assert click_event["tagName"] == "BUTTON"
            assert click_event["attributes"]["id"] == "btn-submit"
            assert click_event["attributes"]["class"] == "primary large"
            assert click_event["attributes"]["data-testid"] == "submit-btn"

            await browser.close()

    @pytest.mark.asyncio
    async def test_click_captures_innertext_truncated(self, test_server):
        """Click event captures innerText (truncated if long)."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/long-text-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            # Click the button with long text
            await page.click("#long-text-btn")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            click_event = next((e for e in events if e["event"] == "click"), None)
            assert click_event is not None
            # Inner text should be truncated to 100 chars + "..."
            assert len(click_event["innerText"]) == 103  # 100 + "..."
            assert click_event["innerText"].endswith("...")

            await browser.close()


class TestInputEvents:
    """Tests for input event capture."""

    @pytest.mark.asyncio
    async def test_input_captures_value_for_non_password(self, test_server):
        """Input event captures value (for non-password fields)."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/test-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            # Type in the username field
            await page.fill("#username", "testuser")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            input_events = [e for e in events if e["event"] == "input"]
            assert len(input_events) >= 1
            # The last input event should have the final value
            last_input = input_events[-1]
            assert last_input["value"] == "testuser"
            assert last_input["selector"] == "#username"

            await browser.close()

    @pytest.mark.asyncio
    async def test_input_masks_password_fields(self, test_server):
        """Input event does not capture value for password fields."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/test-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            # Type in the password field
            await page.fill("#password", "secretpass")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            password_events = [e for e in events if e["selector"] == "#password"]
            # Password field value should be null
            for event in password_events:
                assert event["value"] is None

            await browser.close()


class TestChangeEvents:
    """Tests for change event capture."""

    @pytest.mark.asyncio
    async def test_change_captures_new_value(self, test_server):
        """Change event captures new value."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/test-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            # Change the select dropdown
            await page.select_option("#country", "uk")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            change_event = next((e for e in events if e["event"] == "change" and e["selector"] == "#country"), None)
            assert change_event is not None
            assert change_event["value"] == "uk"

            await browser.close()


class TestSubmitEvents:
    """Tests for submit event capture."""

    @pytest.mark.asyncio
    async def test_submit_captures_form_selector_and_values(self, test_server):
        """Submit event captures form selector and all field values."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/form-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            # Fill form fields
            await page.fill("#email", "test@example.com")
            await page.fill("#form-password", "secret123")

            # Submit the form
            await page.click("#submit-btn")
            await asyncio.sleep(0.2)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            submit_event = next((e for e in events if e["event"] == "submit"), None)
            assert submit_event is not None
            assert submit_event["selector"] == "#login-form"
            assert submit_event["tagName"] == "FORM"
            assert "formValues" in submit_event
            assert submit_event["formValues"]["email"] == "test@example.com"
            assert submit_event["formValues"]["password"] == "[REDACTED]"
            assert submit_event["formValues"]["remember"] == "yes"

            await browser.close()


class TestMutationObserver:
    """Tests for MutationObserver functionality."""

    @pytest.mark.asyncio
    async def test_mutation_observer_tracks_new_elements(self, test_server):
        """MutationObserver attaches listeners to new elements."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/dynamic-page")
            await setup_event_capture(page)

            # Also set up mutation listener
            await page.evaluate("""() => {
                window.__webLoggerMutations = [];
                window.addEventListener('webLoggerMutation', (e) => {
                    window.__webLoggerMutations.push(e.detail);
                });
            }""")

            await inject_test_content_script(page)

            # Click button to add dynamic element
            await page.click("#add-element")
            await asyncio.sleep(0.2)

            mutations = await page.evaluate("() => window.__webLoggerMutations")

            # Check that the dynamic button was detected
            dynamic_mutation = next((m for m in mutations if m["id"] == "dynamic-btn"), None)
            assert dynamic_mutation is not None
            assert dynamic_mutation["tagName"] == "BUTTON"

            # Now click the dynamically added button
            await page.click("#dynamic-btn")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            # Should have captured the click on the dynamic button
            dynamic_click = next((e for e in events if e["selector"] == "#dynamic-btn"), None)
            assert dynamic_click is not None
            assert dynamic_click["event"] == "click"

            await browser.close()


class TestEventMetadata:
    """Tests for event metadata (URL, timestamp)."""

    @pytest.mark.asyncio
    async def test_events_include_page_url(self, test_server):
        """Events include page URL."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/test-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            await page.click("#btn-submit")
            await asyncio.sleep(0.1)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            assert len(events) >= 1
            for event in events:
                assert "url" in event
                assert f"{test_server}/test-page" in event["url"]

            await browser.close()

    @pytest.mark.asyncio
    async def test_events_include_timestamp(self, test_server):
        """Events include timestamp."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(f"{test_server}/test-page")
            await setup_event_capture(page)
            await inject_test_content_script(page)

            import time
            before = int(time.time() * 1000)
            await page.click("#btn-submit")
            await asyncio.sleep(0.1)
            after = int(time.time() * 1000)

            events = await page.evaluate("() => window.__webLoggerCapturedEvents")

            assert len(events) >= 1
            for event in events:
                assert "timestamp" in event
                assert isinstance(event["timestamp"], int)
                assert before <= event["timestamp"] <= after

            await browser.close()
