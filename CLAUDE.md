# Web Interaction & Network Logger

## Project Overview
A hybrid Playwright + browser extension tool that records user interactions (clicks, input changes, form submissions) and network requests while browsing. The captured data will be used to help LLMs understand and reverse-engineer API patterns for building scrapers.

## Architecture

### Hybrid Approach
The tool uses two components working together:

1. **Playwright (Network Capture)**
   - Launches a headed Chromium browser with the extension pre-loaded
   - Intercepts all network traffic with full request/response bodies
   - Auto-filters requests to current domain + subdomains only
   - Manages session lifecycle (start/stop recording, export)

2. **Browser Extension (DOM Interaction Capture)**
   - `manifest.json` — Extension config with required permissions
   - `content.js` — Captures DOM interactions via event listeners
   - Uses MutationObserver to track dynamically added elements (`childList: true`, `subtree: true`)
   - Communicates via three redundant channels:
     1. Console logging: `console.log('WEB_LOGGER_EVENT:' + JSON.stringify(...))`
     2. Window object: `window.__webLoggerEvents__` global array
     3. Chrome runtime: `chrome.runtime.sendMessage()`

### Communication Flow
```
User interacts with page
        ↓
Extension captures DOM event → sends to Playwright via messaging
        ↓
Playwright captures network request/response
        ↓
Both logs merged chronologically → exported to JSON
```

## Key Technical Decisions
- Playwright for network capture (avoids Manifest V3 limitations on response bodies)
- Extension for DOM interactions (direct access to page events)
- MutationObserver for dynamically added elements (SPAs, modals, infinite scroll)
- Auto domain filtering: only capture requests to current page's domain + subdomains
- Minimal sensitive data redaction: form passwords are redacted as `[REDACTED]`, input event passwords return `null`
- File export only (no server required)

## Interactive Element Selector
Clicks are only captured on interactive elements matching:
```javascript
'a, button, input, select, textarea, [onclick], [role="button"], [tabindex]'
```
Generic divs won't capture clicks unless they have proper attributes.

## Captured Element Attributes
Extension captures these specific attributes from interacted elements:
```javascript
['id', 'class', 'name', 'type', 'href', 'src', 'value', 'placeholder', 'data-testid']
```

## Network Capture Details
- **Binary responses**: Returns `"[binary]"` string placeholder for images, PDFs, fonts, etc.
- **Failed requests**: Include `"error"` field with failure info
- **JSON detection**: Uses heuristics (starts with `{` or `[`), not just content-type header

## Data Structures

### Interaction Log Entry
```json
{
  "timestamp": 1706000000000,
  "type": "interaction",
  "event": "click|change|input|submit",
  "selector": "button#submit-btn",
  "tagName": "BUTTON",
  "attributes": {"id": "submit-btn", "class": "primary"},
  "value": null,
  "innerText": "Submit",
  "url": "https://example.com/page"
}
```

### Network Log Entry
```json
{
  "timestamp": 1706000000001,
  "type": "network",
  "url": "https://api.example.com/data",
  "method": "POST",
  "requestHeaders": {},
  "requestBody": {},
  "responseStatus": 200,
  "responseHeaders": {},
  "responseBody": {}
}
```

### Merged Export Format
```json
{
  "session": {
    "startTime": 1706000000000,
    "endTime": 1706000060000,
    "startUrl": "https://example.com",
    "domain": "example.com"
  },
  "events": [
    {"timestamp": ..., "type": "interaction", ...},
    {"timestamp": ..., "type": "network", ...}
  ]
}
```

## Dependencies
- `playwright>=1.40.0` — Browser automation
- `pytest>=8.0.0` — Testing framework
- `pytest-asyncio>=0.23.0` — Async test support
- `tldextract>=5.1.0` — Multi-level TLD extraction (e.g., `.co.uk`)

## Requirements
- Python `>=3.14` (specified in pyproject.toml)

## Commands
- `python -m src.main` — Launch Playwright browser with extension, start recording
- `pytest` — Run all tests (unit + integration)

## Workflow
- Tasks are tracked in `PLAN.md` with status (DONE or pending)
- To continue work: "Do your next task" — read PLAN.md, find the next pending task, implement it with tests, mark as DONE
- After completing a task, run `pytest` to verify all tests pass before marking DONE

## File Structure
```
web-logger/
├── CLAUDE.md
├── PLAN.md
├── pyproject.toml
├── requirements.txt
├── venv/                  — Python 3.14 virtual environment
├── src/
│   ├── __init__.py
│   ├── main.py           — Main entry, Playwright launcher
│   ├── network.py        — Network interception & domain filtering
│   ├── merger.py         — Merge and export logs
│   └── utils.py          — Domain extraction, selector generation
├── extension/
│   ├── manifest.json
│   ├── content.js        — DOM interaction capture + MutationObserver
│   └── background.js     — Message relay to Playwright
├── tests/
│   ├── __init__.py
│   ├── test_setup.py        — Verify project setup
│   ├── test_network.py      — Network capture tests + helper function tests
│   ├── test_merger.py
│   ├── test_utils.py
│   ├── test_extension.py
│   └── test_integration.py  — End-to-end workflow tests
└── logs/                     — Exported session logs
    └── {YYYYMMDDTHHMMSS}_{domain}/
        ├── session.json      — Event log (interactions + network)
        └── initial_dom.html  — Initial page DOM snapshot after load
```

## Domain Filtering Logic
Given a page URL `https://shop.example.com/products`:
- Extract root domain: `example.com`
- Capture requests to: `example.com`, `*.example.com`
- Ignore: `google-analytics.com`, `facebook.com`, `cdn.jsdelivr.net`, etc.

## LLM Output Format
Final export is chronologically ordered, merging interactions and requests, so an LLM can trace: "User clicked X → triggered POST to /api/Y with body Z"
