# Implementation Plan

## Task 1: Project Setup — DONE

### Description
Initialize the Python project with required dependencies and folder structure.

### Subtasks
- [x] Create Python 3.14 virtual environment
- [x] Set up direnv for auto-activation
- [x] Create `requirements.txt` with dependencies
- [x] Create `pyproject.toml` with pytest configuration
- [x] Install dependencies: `playwright`, `pytest`, `pytest-asyncio`
- [x] Install Playwright Chromium browser
- [x] Create folder structure: `src/`, `extension/`, `tests/`, `logs/`

### Dependencies
- playwright
- pytest
- pytest-asyncio
- tldextract

### Unit Tests (`tests/test_setup.py`)
- [x] `test_python_version` — Verify Python 3.14+ is used
- [x] `test_playwright_import` — Verify sync playwright is importable
- [x] `test_playwright_async_import` — Verify async playwright is importable
- [x] `test_folder_structure` — Verify required folders exist

---

## Task 2: Utils Module (`src/utils.py`) — DONE

### Description
Utility functions for domain extraction and CSS selector generation.

### Functions
```python
extract_root_domain(url: str) -> str
    # "https://shop.example.com/path" → "example.com"

is_subdomain_of(url: str, root_domain: str) -> bool
    # Check if URL belongs to domain/subdomain

generate_selector(element: dict) -> str
    # Generate unique CSS selector for an element

# Helper functions (internal)
def _is_ip_address(hostname: str) -> bool:
    # Detects IPv4 and IPv6 addresses
```

### Unit Tests (`tests/test_utils.py`)
- [x] `extractRootDomain` handles standard URLs
- [x] `extractRootDomain` handles URLs with ports
- [x] `extractRootDomain` handles localhost
- [x] `extractRootDomain` handles IP addresses
- [x] `extractRootDomain` handles multi-level TLDs (e.g., `.co.uk`)
- [x] `isSubdomainOf` returns true for exact domain match
- [x] `isSubdomainOf` returns true for subdomain match
- [x] `isSubdomainOf` returns false for different domain
- [x] `generateSelector` creates selector with ID when available
- [x] `generateSelector` creates selector with classes when no ID
- [x] `generateSelector` creates nth-child selector as fallback

---

## Task 3: Network Module (`src/network.py`) — DONE

### Description
Playwright network interception with domain filtering and request/response capture.

### Functions
```python
async def setup_network_capture(page: Page, root_domain: str, on_request: Callable) -> None:
    # - Intercepts all requests
    # - Filters to root_domain + subdomains
    # - Captures full request/response bodies
    # - Calls on_request callback with log entry

# Helper functions (internal)
def _get_request_body(request: Request) -> str | dict | None:
    # Extracts & parses request body (JSON or raw string)

async def _get_response_body(response: Response) -> str | dict | None:
    # Handles content-type negotiation, JSON parsing, binary detection

def _is_binary_content_type(content_type: str) -> bool:
    # Identifies binary content types (images, PDFs, fonts, etc.)

async def handle_request_failed(request: Request) -> None:
    # Captures failed network requests with error info
```

### Unit Tests (`tests/test_network.py`)
- [x] Captures requests to exact root domain
- [x] Captures requests to subdomains
- [x] Ignores requests to different domains
- [x] Captures GET request with query params
- [x] Captures POST request with JSON body
- [x] Captures POST request with form data
- [x] Captures response status and headers
- [x] Captures response body (JSON)
- [x] Captures response body (text/html)
- [x] Handles binary responses gracefully (skip or base64)
- [x] Handles failed requests (network error)
- [x] Includes accurate timestamps

---

## Task 4: Browser Extension — DONE

### Description
Chrome extension (Manifest V3) to capture DOM interactions.

### Files

#### `extension/manifest.json`
- Manifest V3 configuration
- Permissions: `activeTab`, `scripting`
- Content script injection

#### `extension/content.js`
- Event listeners: `click`, `input`, `change`, `submit`
- MutationObserver for dynamically added elements
- Selector generation for interacted elements
- Send events to background script

#### `extension/background.js`
- Relay messages from content script
- Expose events via `chrome.runtime` for Playwright to consume

### Unit Tests (`tests/test_extension.py`)
- [x] Click event captures element selector, tagName, attributes
- [x] Click event captures innerText (truncated if long)
- [x] Input event captures value (for non-password fields)
- [x] Change event captures new value
- [x] Submit event captures form selector and all field values
- [x] MutationObserver attaches listeners to new elements
- [x] Events include page URL
- [x] Events include timestamp

---

## Task 5: Merger Module (`src/merger.py`) — DONE

### Description
Merge interaction and network logs chronologically, export to JSON file.

### Functions
```python
def create_session(start_url: str) -> dict:
    # Initialize session object

def add_event(session: dict, event: dict) -> None:
    # Add interaction or network event

def finalize_session(session: dict) -> None:
    # Set end_time, sort events

def export_session(session: dict, filepath: str) -> None:
    # Write to JSON file
```

### Unit Tests (`tests/test_merger.py`)
- [x] `createSession` extracts domain from startUrl
- [x] `addEvent` adds interaction events
- [x] `addEvent` adds network events
- [x] `finalizeSession` sorts events by timestamp
- [x] `finalizeSession` sets correct endTime
- [x] `exportSession` writes valid JSON file
- [x] `exportSession` creates logs directory if missing
- [x] Merged output interleaves interactions and network correctly

---

## Task 6: Main Entry (`src/main.py`) — DONE

### Description
Orchestrate Playwright browser launch, extension loading, and recording session.

### Functions
```python
async def poll_extension_events(page: Page, session: dict) -> None:
    # Polls window.__webLoggerEvents__ from page context

async def inject_event_collector(page: Page) -> None:
    # Initializes global event array for extension

async def setup_page_listeners(page: Page, session: dict, root_domain: str) -> None:
    # Consolidated listener setup (network + events + console)

async def create_browser_context(playwright) -> BrowserContext:
    # Launches persistent context with extension

async def run_recording_session(start_url: str | None = None) -> str:
    # Main recording session orchestration
```

### Features
- Launch Chromium with extension loaded
- Navigate to start URL (or open blank page)
- Set up network capture with domain filter
- Listen for interaction events from extension
- Signal handling (SIGINT/SIGTERM) with Windows fallback
- Console message handler for `WEB_LOGGER_EVENT:` prefix
- Multi-tab support via `context.on("page", ...)`
- Domain extraction on first navigation (updates session if no start URL)
- Handle Ctrl+C to stop recording and export
- Export merged JSON to `logs/` folder

### Flow
```
1. Parse CLI args (optional start URL)
2. Launch Playwright browser with extension
3. Extract root domain from first navigation
4. Set up network interception
5. Set up extension message listener
6. Wait for user to browse
7. On exit: finalize and export session
```

### Unit Tests (`tests/test_main.py`)
Integration tests:
- [x] Browser launches with extension loaded
- [x] Network requests are captured
- [x] DOM interactions are captured (via polling)
- [x] Export file contains both event types
- [x] Domain filtering works correctly

---

## Task 7: Integration Testing (`tests/test_integration.py`) — DONE

### Description
End-to-end tests to verify the complete workflow.

### Test Classes
- `TestUtilsIntegration` — Utils module integration tests
- `TestNetworkIntegration` — Network capture integration tests
- `TestMergerIntegration` — Session merge/export integration tests
- `TestExtensionContentScript` — Content script integration tests
- `TestMainIntegration` — Main module integration tests
- `TestFullWorkflow` — Complete end-to-end workflow tests

### Test Scenarios
- [x] Record session on a test page with clicks and API calls
- [x] Verify interactions and network events are merged
- [x] Verify timestamps are chronologically ordered
- [x] Verify domain filtering excludes third-party requests
- [x] Verify dynamic elements (added via JS) are tracked

---

## Implementation Order

1. **Task 1: Project Setup** — Foundation
2. **Task 2: Utils Module** — No dependencies, testable in isolation
3. **Task 5: Merger Module** — Depends on utils, testable in isolation
4. **Task 3: Network Module** — Depends on utils, requires Playwright
5. **Task 4: Browser Extension** — Independent, can parallel with Task 3
6. **Task 6: Main Entry** — Integrates all modules
7. **Task 7: Integration Testing** — Final validation

---

## Task 8: Session Folder Structure + Initial DOM Capture — DONE

### Description
Modify the logs output to use session subfolders with datetime and domain naming, and capture the initial DOM as a separate HTML file.

### New Folder Structure
```
logs/
└── 20250128T143045_example_com/
    ├── session.json          # Event log (renamed from session_*.json)
    └── initial_dom.html      # Full HTML snapshot after page load
```

### Changes Made

#### `src/main.py`
- Added `capture_initial_dom(page: Page) -> str` function to capture full HTML
- Modified export logic to create session subfolders with `YYYYMMDDTHHMMSS_domain` naming
- Captures initial DOM after page navigation (with or without start URL)
- Writes `session.json` and `initial_dom.html` to session folder

#### `tests/test_main.py`
- Added `TestInitialDomCapture` class:
  - `test_capture_initial_dom_returns_html` — Verifies HTML content is returned
  - `test_capture_initial_dom_contains_page_content` — Verifies page content is captured
- Added `TestSessionFolderStructure` class:
  - `test_session_folder_name_format` — Verifies `YYYYMMDDTHHMMSS_domain` pattern
  - `test_session_folder_contains_expected_files` — Verifies both files are created

### Unit Tests
- [x] `capture_initial_dom` returns valid HTML with `<html>`, `<head>`, `<body>` tags
- [x] `capture_initial_dom` contains actual page content
- [x] Session folder name matches `YYYYMMDDTHHMMSS_domain` pattern
- [x] Session folder contains `session.json` and `initial_dom.html`

---

## Task 9: CLI Arguments and Log Folder Structure Changes — DONE

### Description
Modify the web-activity-logger to require `--tag` and `--url` CLI arguments, and reorganize log folder structure.

### Changes Made

#### `src/utils.py`
- Added `extract_domain_name(url)` function to extract domain name without TLD
  - `"https://www.allianz.com.tr/path"` → `"allianz"`
  - `"https://shop.example.co.uk/path"` → `"example"`

#### `src/main.py`
- Changed CLI to require `--tag` and `--url` arguments (previously optional positional URL)
- Changed `run_recording_session(start_url: str | None = None)` to `run_recording_session(start_url: str, tag: str)`
- Changed datetime format from `%Y%m%dT%H%M%S` to `%Y%m%d_%H%M%S`
- Changed folder structure from `logs/{datetime}_{domain_with_underscores}/` to `logs/{tag}/{domain_name}/{datetime}/`
- Removed code handling optional URL (simplified main loop)

#### `tests/test_utils.py`
- Added `TestExtractDomainName` class with tests for standard URLs, multi-level TLDs, localhost, and IP addresses

#### `tests/test_main.py`
- Updated `TestSessionFolderStructure` for new folder pattern `logs/{tag}/{domain}/{YYYYMMDD_HHMMSS}/`
- Added `TestCLIArguments` to verify required arguments

#### `CLAUDE.md`
- Updated Commands section with new CLI syntax
- Updated File Structure section with new folder layout
- Documented `extract_domain_name` function

### Example Usage
```bash
python -m src.main --tag=health --url="https://www.allianz.com.tr/tr_TR/"
# Output: logs/health/allianz/20260130_173732/session.json
```

---

## Test Commands

```bash
pytest                      # Run all unit tests
pytest tests/test_utils.py  # Run utils tests only
pytest tests/test_network.py # Run network tests only
pytest -k "integration"     # Run integration tests
```
