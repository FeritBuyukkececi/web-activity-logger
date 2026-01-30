"""Tests for src/utils.py"""

import pytest

from src.utils import extract_domain_name, extract_root_domain, generate_selector, is_subdomain_of


class TestExtractRootDomain:
    """Tests for extract_root_domain function."""

    def test_standard_url(self):
        """extractRootDomain handles standard URLs."""
        assert extract_root_domain("https://shop.example.com/path") == "example.com"
        assert extract_root_domain("https://www.example.com/") == "example.com"
        assert extract_root_domain("http://example.com/page.html") == "example.com"

    def test_url_with_port(self):
        """extractRootDomain handles URLs with ports."""
        assert extract_root_domain("http://example.com:8080/path") == "example.com"
        assert extract_root_domain("https://shop.example.com:443/") == "example.com"

    def test_localhost(self):
        """extractRootDomain handles localhost."""
        assert extract_root_domain("http://localhost/path") == "localhost"
        assert extract_root_domain("http://localhost:3000/") == "localhost"

    def test_ip_address(self):
        """extractRootDomain handles IP addresses."""
        assert extract_root_domain("http://192.168.1.1/path") == "192.168.1.1"
        assert extract_root_domain("http://10.0.0.1:8080/") == "10.0.0.1"
        assert extract_root_domain("http://127.0.0.1/") == "127.0.0.1"

    def test_multi_level_tld(self):
        """extractRootDomain handles multi-level TLDs (e.g., .co.uk)."""
        assert extract_root_domain("https://shop.example.co.uk/path") == "example.co.uk"
        assert extract_root_domain("https://www.example.com.au/") == "example.com.au"
        assert extract_root_domain("https://sub.domain.example.org.uk/") == "example.org.uk"


class TestExtractDomainName:
    """Tests for extract_domain_name function."""

    def test_standard_url(self):
        """extract_domain_name handles standard URLs."""
        assert extract_domain_name("https://shop.example.com/path") == "example"
        assert extract_domain_name("https://www.example.com/") == "example"
        assert extract_domain_name("http://example.com/page.html") == "example"

    def test_multi_level_tld(self):
        """extract_domain_name handles multi-level TLDs (e.g., .co.uk, .com.tr)."""
        assert extract_domain_name("https://www.allianz.com.tr/path") == "allianz"
        assert extract_domain_name("https://shop.example.co.uk/path") == "example"
        assert extract_domain_name("https://www.example.com.au/") == "example"

    def test_localhost(self):
        """extract_domain_name handles localhost."""
        assert extract_domain_name("http://localhost/path") == "localhost"
        assert extract_domain_name("http://localhost:3000/") == "localhost"

    def test_ip_address(self):
        """extract_domain_name handles IP addresses."""
        assert extract_domain_name("http://192.168.1.1/path") == "192.168.1.1"
        assert extract_domain_name("http://10.0.0.1:8080/") == "10.0.0.1"
        assert extract_domain_name("http://127.0.0.1/") == "127.0.0.1"


class TestIsSubdomainOf:
    """Tests for is_subdomain_of function."""

    def test_exact_domain_match(self):
        """isSubdomainOf returns true for exact domain match."""
        assert is_subdomain_of("https://example.com/path", "example.com") is True
        assert is_subdomain_of("http://example.com:8080/", "example.com") is True

    def test_subdomain_match(self):
        """isSubdomainOf returns true for subdomain match."""
        assert is_subdomain_of("https://shop.example.com/path", "example.com") is True
        assert is_subdomain_of("https://api.v2.example.com/", "example.com") is True
        assert is_subdomain_of("https://www.example.com/", "example.com") is True

    def test_different_domain(self):
        """isSubdomainOf returns false for different domain."""
        assert is_subdomain_of("https://other.com/path", "example.com") is False
        assert is_subdomain_of("https://example.org/", "example.com") is False
        assert is_subdomain_of("https://notexample.com/", "example.com") is False
        # Edge case: domain that contains the root but isn't a subdomain
        assert is_subdomain_of("https://fakeexample.com/", "example.com") is False


class TestGenerateSelector:
    """Tests for generate_selector function."""

    def test_selector_with_id(self):
        """generateSelector creates selector with ID when available."""
        element = {
            "tagName": "BUTTON",
            "attributes": {"id": "submit-btn", "class": "primary"},
        }
        assert generate_selector(element) == "#submit-btn"

    def test_selector_with_classes(self):
        """generateSelector creates selector with classes when no ID."""
        element = {"tagName": "DIV", "attributes": {"class": "card primary"}}
        assert generate_selector(element) == "div.card.primary"

        # Single class
        element = {"tagName": "SPAN", "attributes": {"class": "highlight"}}
        assert generate_selector(element) == "span.highlight"

    def test_selector_nth_child_fallback(self):
        """generateSelector creates nth-child selector as fallback."""
        # No ID or class
        element = {"tagName": "LI", "attributes": {}, "index": 3}
        assert generate_selector(element) == "li:nth-child(3)"

        # Empty class
        element = {"tagName": "P", "attributes": {"class": ""}, "index": 1}
        assert generate_selector(element) == "p:nth-child(1)"

        # No attributes at all
        element = {"tagName": "DIV", "index": 5}
        assert generate_selector(element) == "div:nth-child(5)"
