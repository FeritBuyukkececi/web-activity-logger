"""Main entry point for the web logger.

Orchestrates Playwright browser launch, extension loading, and recording session.
"""

import argparse
import asyncio
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page

from .merger import add_event, create_session, export_session, finalize_session
from .network import setup_network_capture
from .utils import extract_root_domain


# Extension directory path (relative to this file)
EXTENSION_DIR = Path(__file__).parent.parent / "extension"


async def capture_initial_dom(page: Page) -> str:
    """Capture the full HTML of the page after initial load."""
    return await page.content()


async def poll_extension_events(page: Page, session: dict) -> None:
    """
    Poll the extension for captured interaction events.

    The extension stores events in window.__webLoggerEvents__ which we
    retrieve and clear periodically.
    """
    try:
        events = await page.evaluate("""
            () => {
                if (typeof window.__webLoggerEvents__ !== 'undefined') {
                    const events = window.__webLoggerEvents__.splice(0);
                    return events;
                }
                return [];
            }
        """)

        for event in events:
            add_event(session, event)

    except Exception:
        # Page might be navigating or closed
        pass


async def inject_event_collector(page: Page) -> None:
    """
    Inject a script that collects events from the content script.

    This creates a global array that the content script can push to,
    which we then poll from Python.
    """
    try:
        await page.evaluate("""
            () => {
                if (typeof window.__webLoggerEvents__ === 'undefined') {
                    window.__webLoggerEvents__ = [];
                }
            }
        """)
    except Exception:
        pass


async def setup_page_listeners(page: Page, session: dict, root_domain: str) -> None:
    """Set up all listeners on a page."""
    # Inject event collector
    await inject_event_collector(page)

    # Set up network capture
    def on_network_event(event: dict) -> None:
        add_event(session, event)

    await setup_network_capture(page, root_domain, on_network_event)

    # Listen for console messages from the extension
    def handle_console(msg):
        if msg.text.startswith("WEB_LOGGER_EVENT:"):
            try:
                import json
                event_json = msg.text[len("WEB_LOGGER_EVENT:"):]
                event = json.loads(event_json)
                add_event(session, event)
            except Exception:
                pass

    page.on("console", handle_console)


async def create_browser_context(playwright) -> BrowserContext:
    """
    Launch a browser with the extension loaded.

    Returns a BrowserContext with the extension pre-loaded.
    """
    extension_path = str(EXTENSION_DIR.resolve())

    # Playwright requires launching persistent context to load extensions
    user_data_dir = Path(__file__).parent.parent / ".playwright-profile"
    user_data_dir.mkdir(exist_ok=True)

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        headless=False,
        args=[
            f"--disable-extensions-except={extension_path}",
            f"--load-extension={extension_path}",
        ],
    )

    return context


async def run_recording_session(start_url: str | None = None) -> str:
    """
    Run the main recording session.

    Args:
        start_url: Optional URL to navigate to on start.

    Returns:
        Path to the exported log file.
    """
    async with async_playwright() as playwright:
        print("Launching browser with extension...")
        context = await create_browser_context(playwright)

        # Get or create the first page
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()

        # Track initial DOM capture
        initial_dom = None

        # Navigate to start URL if provided
        if start_url:
            print(f"Navigating to {start_url}...")
            await page.goto(start_url)
            await page.wait_for_load_state("domcontentloaded")
            initial_dom = await capture_initial_dom(page)
            root_domain = extract_root_domain(start_url)
        else:
            # Wait for user to navigate somewhere
            root_domain = None
            print("No start URL provided. Navigate to a page to begin recording.")
            print("Domain filtering will be based on the first navigation.")

        # Create session (use placeholder if no URL yet)
        session_url = start_url or "about:blank"
        session = create_session(session_url)

        # Track if we have set up listeners
        listeners_setup = False

        # Event to signal shutdown
        shutdown_event = asyncio.Event()

        def signal_handler():
            print("\nStopping recording...")
            shutdown_event.set()

        # Set up signal handler for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda s, f: signal_handler())

        # Handle new pages (tabs)
        async def on_new_page(new_page: Page):
            nonlocal root_domain, listeners_setup
            if root_domain and listeners_setup:
                await setup_page_listeners(new_page, session, root_domain)

        context.on("page", lambda p: asyncio.create_task(on_new_page(p)))

        # Main loop
        print("\nRecording started. Press Ctrl+C to stop and export.")
        print("-" * 50)

        try:
            while not shutdown_event.is_set():
                # Check if we need to set up listeners (first navigation)
                if not listeners_setup:
                    current_url = page.url
                    if current_url and current_url != "about:blank":
                        if root_domain is None:
                            root_domain = extract_root_domain(current_url)
                            session["session"]["startUrl"] = current_url
                            session["session"]["domain"] = root_domain

                        # Capture initial DOM if not already captured
                        if initial_dom is None:
                            initial_dom = await capture_initial_dom(page)

                        print(f"Recording for domain: {root_domain}")
                        await setup_page_listeners(page, session, root_domain)
                        listeners_setup = True

                # Poll for extension events
                if listeners_setup:
                    for p in context.pages:
                        await poll_extension_events(p, session)

                # Small delay to prevent busy loop
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass

        except Exception as e:
            print(f"Error during recording: {e}")

        # Finalize and export
        print("\nFinalizing session...")
        finalize_session(session)

        # Generate session folder name: YYYYMMDDTHHMMSS_domain
        dt_str = datetime.now().strftime("%Y%m%dT%H%M%S")
        domain_part = root_domain.replace(".", "_") if root_domain else "unknown"
        session_folder = f"{dt_str}_{domain_part}"

        logs_dir = Path(__file__).parent.parent / "logs"
        session_dir = logs_dir / session_folder
        session_dir.mkdir(parents=True, exist_ok=True)

        # Export session JSON
        session_filepath = session_dir / "session.json"
        export_session(session, str(session_filepath))

        # Export initial DOM (if captured)
        if initial_dom:
            dom_filepath = session_dir / "initial_dom.html"
            dom_filepath.write_text(initial_dom, encoding="utf-8")
            print(f"Initial DOM saved to: {dom_filepath}")

        print(f"Session exported to: {session_filepath}")

        # Clean up - browser may already be closing due to signal
        try:
            await context.close()
        except Exception:
            pass  # Browser already closed, which is fine

        return str(session_filepath)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Web Interaction & Network Logger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                      # Start with blank page
  python -m src.main https://example.com  # Start at specific URL
        """,
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Optional start URL to navigate to",
    )

    args = parser.parse_args()

    try:
        filepath = asyncio.run(run_recording_session(args.url))
        print(f"\nDone! Log saved to: {filepath}")
    except KeyboardInterrupt:
        print("\nRecording interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
