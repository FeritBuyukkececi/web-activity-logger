"""Unit tests for the merger module."""

import json
import os
import tempfile
import time
from unittest import mock

import pytest

from src.merger import add_event, create_session, export_session, finalize_session


class TestCreateSession:
    """Tests for create_session function."""

    def test_extracts_domain_from_start_url(self):
        """createSession extracts domain from startUrl."""
        session = create_session("https://shop.example.com/products")

        assert session["session"]["domain"] == "example.com"
        assert session["session"]["startUrl"] == "https://shop.example.com/products"

    def test_sets_start_time(self):
        """createSession sets startTime to current timestamp in milliseconds."""
        before = int(time.time() * 1000)
        session = create_session("https://example.com")
        after = int(time.time() * 1000)

        assert before <= session["session"]["startTime"] <= after

    def test_initializes_empty_events_list(self):
        """createSession initializes an empty events list."""
        session = create_session("https://example.com")

        assert session["events"] == []

    def test_end_time_is_none_initially(self):
        """createSession sets endTime to None initially."""
        session = create_session("https://example.com")

        assert session["session"]["endTime"] is None


class TestAddEvent:
    """Tests for add_event function."""

    def test_adds_interaction_event(self):
        """addEvent adds interaction events."""
        session = create_session("https://example.com")
        interaction = {
            "timestamp": 1706000000000,
            "type": "interaction",
            "event": "click",
            "selector": "button#submit",
            "tagName": "BUTTON",
            "attributes": {"id": "submit"},
            "value": None,
            "innerText": "Submit",
            "url": "https://example.com/page",
        }

        add_event(session, interaction)

        assert len(session["events"]) == 1
        assert session["events"][0] == interaction

    def test_adds_network_event(self):
        """addEvent adds network events."""
        session = create_session("https://example.com")
        network = {
            "timestamp": 1706000000001,
            "type": "network",
            "url": "https://api.example.com/data",
            "method": "POST",
            "requestHeaders": {"Content-Type": "application/json"},
            "requestBody": {"key": "value"},
            "responseStatus": 200,
            "responseHeaders": {},
            "responseBody": {"result": "success"},
        }

        add_event(session, network)

        assert len(session["events"]) == 1
        assert session["events"][0] == network

    def test_adds_multiple_events(self):
        """addEvent can add multiple events."""
        session = create_session("https://example.com")

        add_event(session, {"timestamp": 1, "type": "interaction"})
        add_event(session, {"timestamp": 2, "type": "network"})
        add_event(session, {"timestamp": 3, "type": "interaction"})

        assert len(session["events"]) == 3


class TestFinalizeSession:
    """Tests for finalize_session function."""

    def test_sorts_events_by_timestamp(self):
        """finalizeSession sorts events by timestamp."""
        session = create_session("https://example.com")
        add_event(session, {"timestamp": 3000, "type": "network"})
        add_event(session, {"timestamp": 1000, "type": "interaction"})
        add_event(session, {"timestamp": 2000, "type": "interaction"})

        finalize_session(session)

        timestamps = [e["timestamp"] for e in session["events"]]
        assert timestamps == [1000, 2000, 3000]

    def test_sets_correct_end_time(self):
        """finalizeSession sets correct endTime."""
        session = create_session("https://example.com")

        before = int(time.time() * 1000)
        finalize_session(session)
        after = int(time.time() * 1000)

        assert before <= session["session"]["endTime"] <= after

    def test_end_time_after_start_time(self):
        """finalizeSession sets endTime after startTime."""
        session = create_session("https://example.com")
        finalize_session(session)

        assert session["session"]["endTime"] >= session["session"]["startTime"]

    def test_interleaves_interactions_and_network_correctly(self):
        """Merged output interleaves interactions and network correctly."""
        session = create_session("https://example.com")

        # Add events in non-chronological order with mixed types
        add_event(session, {"timestamp": 100, "type": "interaction", "event": "click"})
        add_event(session, {"timestamp": 300, "type": "network", "url": "/api/2"})
        add_event(session, {"timestamp": 200, "type": "network", "url": "/api/1"})
        add_event(session, {"timestamp": 400, "type": "interaction", "event": "input"})
        add_event(session, {"timestamp": 250, "type": "interaction", "event": "change"})

        finalize_session(session)

        # Verify chronological order with interleaved types
        events = session["events"]
        assert len(events) == 5
        assert events[0]["timestamp"] == 100
        assert events[0]["type"] == "interaction"
        assert events[1]["timestamp"] == 200
        assert events[1]["type"] == "network"
        assert events[2]["timestamp"] == 250
        assert events[2]["type"] == "interaction"
        assert events[3]["timestamp"] == 300
        assert events[3]["type"] == "network"
        assert events[4]["timestamp"] == 400
        assert events[4]["type"] == "interaction"


class TestExportSession:
    """Tests for export_session function."""

    def test_writes_valid_json_file(self):
        """exportSession writes valid JSON file."""
        session = create_session("https://example.com")
        add_event(session, {"timestamp": 1000, "type": "interaction"})
        finalize_session(session)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "session.json")
            export_session(session, filepath)

            # Verify file exists and contains valid JSON
            assert os.path.exists(filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            assert loaded == session

    def test_creates_logs_directory_if_missing(self):
        """exportSession creates logs directory if missing."""
        session = create_session("https://example.com")
        finalize_session(session)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create path with non-existent subdirectory
            filepath = os.path.join(tmpdir, "logs", "nested", "session.json")

            export_session(session, filepath)

            assert os.path.exists(filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == session

    def test_exports_complete_session_structure(self):
        """exportSession exports the complete session structure."""
        session = create_session("https://shop.example.com/products")
        add_event(
            session,
            {
                "timestamp": 1706000000000,
                "type": "interaction",
                "event": "click",
                "selector": "button#buy",
                "tagName": "BUTTON",
                "attributes": {"id": "buy"},
                "value": None,
                "innerText": "Buy Now",
                "url": "https://shop.example.com/products",
            },
        )
        add_event(
            session,
            {
                "timestamp": 1706000000100,
                "type": "network",
                "url": "https://api.example.com/cart",
                "method": "POST",
                "requestHeaders": {},
                "requestBody": {"product_id": 123},
                "responseStatus": 200,
                "responseHeaders": {},
                "responseBody": {"success": True},
            },
        )
        finalize_session(session)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "session.json")
            export_session(session, filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            # Verify structure
            assert "session" in loaded
            assert "events" in loaded
            assert loaded["session"]["domain"] == "example.com"
            assert loaded["session"]["startUrl"] == "https://shop.example.com/products"
            assert loaded["session"]["startTime"] is not None
            assert loaded["session"]["endTime"] is not None
            assert len(loaded["events"]) == 2

    def test_handles_unicode_content(self):
        """exportSession handles unicode content correctly."""
        session = create_session("https://example.com")
        add_event(
            session,
            {
                "timestamp": 1000,
                "type": "interaction",
                "innerText": "日本語テスト 🎉",
            },
        )
        finalize_session(session)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "session.json")
            export_session(session, filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            assert loaded["events"][0]["innerText"] == "日本語テスト 🎉"
