"""Utility functions for domain extraction and CSS selector generation."""

from urllib.parse import urlparse

import tldextract


def extract_root_domain(url: str) -> str:
    """
    Extract the root domain from a URL.

    Examples:
        "https://shop.example.com/path" -> "example.com"
        "http://example.com:8080/path" -> "example.com"
        "http://localhost/path" -> "localhost"
        "http://192.168.1.1/path" -> "192.168.1.1"
        "https://shop.example.co.uk/path" -> "example.co.uk"
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Handle localhost
    if hostname == "localhost":
        return "localhost"

    # Handle IP addresses
    if _is_ip_address(hostname):
        return hostname

    # Use tldextract for proper domain extraction (handles multi-level TLDs)
    extracted = tldextract.extract(url)

    if extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    else:
        # No TLD found, return the domain part
        return extracted.domain or hostname


def _is_ip_address(hostname: str) -> bool:
    """Check if hostname is an IP address."""
    # IPv4 check
    parts = hostname.split(".")
    if len(parts) == 4:
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            pass

    # IPv6 check (contains colons)
    if ":" in hostname:
        return True

    return False


def extract_domain_name(url: str) -> str:
    """
    Extract just the domain name (without TLD) from a URL.

    Examples:
        "https://www.allianz.com.tr/path" -> "allianz"
        "https://shop.example.co.uk/path" -> "example"
        "http://localhost/path" -> "localhost"
        "http://192.168.1.1/path" -> "192.168.1.1"
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Handle localhost
    if hostname == "localhost":
        return "localhost"

    # Handle IP addresses
    if _is_ip_address(hostname):
        return hostname

    # Use tldextract for proper domain extraction
    extracted = tldextract.extract(url)

    return extracted.domain or hostname


def is_subdomain_of(url: str, root_domain: str) -> bool:
    """
    Check if a URL belongs to a domain or its subdomains.

    Examples:
        is_subdomain_of("https://example.com/path", "example.com") -> True
        is_subdomain_of("https://shop.example.com/path", "example.com") -> True
        is_subdomain_of("https://other.com/path", "example.com") -> False
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # Exact match
    if hostname == root_domain:
        return True

    # Subdomain match: hostname ends with .root_domain
    if hostname.endswith(f".{root_domain}"):
        return True

    return False


def generate_selector(element: dict) -> str:
    """
    Generate a unique CSS selector for an element.

    Priority:
    1. ID selector (#id)
    2. Tag + class selector (tag.class1.class2)
    3. nth-child fallback (tag:nth-child(n))

    Args:
        element: dict with keys:
            - tagName: str (required)
            - attributes: dict (optional, may contain 'id', 'class')
            - index: int (optional, 1-based index for nth-child)
    """
    tag_name = element.get("tagName", "div").lower()
    attributes = element.get("attributes", {})

    # Priority 1: ID selector
    element_id = attributes.get("id")
    if element_id:
        return f"#{element_id}"

    # Priority 2: Tag + class selector
    class_attr = attributes.get("class", "")
    if class_attr:
        # Split classes and filter empty strings
        classes = [c for c in class_attr.split() if c]
        if classes:
            class_selector = ".".join(classes)
            return f"{tag_name}.{class_selector}"

    # Priority 3: nth-child fallback
    index = element.get("index", 1)
    return f"{tag_name}:nth-child({index})"
