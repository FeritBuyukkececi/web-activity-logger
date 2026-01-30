# Web Activity Logger

A hybrid Playwright + browser extension tool that records user interactions (clicks, input changes, form submissions) and network requests while browsing. The captured data helps LLMs understand and reverse-engineer API patterns for building scrapers.

## Features

- **Network Capture**: Intercepts all HTTP requests/responses with full bodies via Playwright
- **DOM Interaction Tracking**: Captures clicks, inputs, form submissions via browser extension
- **Domain Filtering**: Auto-filters to only capture requests to the current domain + subdomains
- **Dynamic Element Support**: Uses MutationObserver to track dynamically added elements (SPAs, modals, infinite scroll)
- **Chronological Merge**: Combines interaction and network events into a single timeline
- **Initial DOM Snapshot**: Captures the full HTML state after page load

## Requirements

- Python 3.14+
- Chromium (installed via Playwright)

## Installation

```bash
# Clone the repository
git clone https://github.com/FeritBuyukkececi/web-activity-logger.git
cd web-activity-logger

# Create virtual environment
python3.14 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Usage

```bash
# Start recording with tag and URL (both required)
python -m src.main --tag=health --url="https://www.allianz.com.tr/tr_TR/"

# Another example
python -m src.main --tag=finance --url="https://example.com/products"
```

Arguments:
- `--tag`: Required. Tag for organizing logs (e.g., health, finance, ecommerce)
- `--url`: Required. URL to navigate to and start recording

Press `Ctrl+C` to stop recording and export the session.

## Output

Sessions are saved to `logs/` with the following structure:

```
logs/
└── {tag}/                    # Tag-based organization (e.g., health, finance)
    └── {domain}/             # Domain name without TLD (e.g., allianz, example)
        └── {YYYYMMDD_HHMMSS}/  # Session timestamp
            ├── session.json      # Merged interaction + network events
            └── initial_dom.html  # Initial page DOM snapshot
```

Example: `logs/health/allianz/20260130_173732/session.json`

### Session JSON Format

```json
{
  "session": {
    "startTime": 1706000000000,
    "endTime": 1706000060000,
    "startUrl": "https://example.com",
    "domain": "example.com"
  },
  "events": [
    {
      "timestamp": 1706000000000,
      "type": "interaction",
      "event": "click",
      "selector": "button#submit-btn",
      "tagName": "BUTTON",
      "attributes": {"id": "submit-btn", "class": "primary"},
      "innerText": "Submit",
      "url": "https://example.com/page"
    },
    {
      "timestamp": 1706000000001,
      "type": "network",
      "url": "https://api.example.com/data",
      "method": "POST",
      "requestHeaders": {},
      "requestBody": {"key": "value"},
      "responseStatus": 200,
      "responseHeaders": {},
      "responseBody": {"result": "success"}
    }
  ]
}
```

## Architecture

The tool uses two components working together:

1. **Playwright (Network Capture)**
   - Launches a headed Chromium browser with the extension pre-loaded
   - Intercepts all network traffic with full request/response bodies
   - Auto-filters requests to current domain + subdomains only

2. **Browser Extension (DOM Interaction Capture)**
   - Captures DOM interactions via event listeners
   - Uses MutationObserver to track dynamically added elements
   - Communicates with Playwright via console logging and window globals

### Captured Interactions

- **Clicks**: On interactive elements (`a`, `button`, `input`, `select`, `textarea`, `[onclick]`, `[role="button"]`, `[tabindex]`)
- **Input**: Text input changes (passwords are masked)
- **Change**: Select/checkbox/radio changes
- **Submit**: Form submissions with all field values

### Captured Element Attributes

```javascript
['id', 'class', 'name', 'type', 'href', 'src', 'value', 'placeholder', 'data-testid']
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_network.py

# Run with verbose output
pytest -v
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
