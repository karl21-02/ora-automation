"""Tests for PipelineCancelled, _check_cancel, cancel_event."""
from __future__ import annotations

import threading

import pytest

from ora_rd_orchestrator.types import PipelineCancelled


class TestPipelineCancelled:
    def test_is_exception(self):
        exc = PipelineCancelled("test")
        assert isinstance(exc, Exception)
        assert str(exc) == "test"

    def test_raise_and_catch(self):
        with pytest.raises(PipelineCancelled):
            raise PipelineCancelled("cancelled!")


class TestCheckCancel:
    def _get_check_cancel(self):
        """Import _check_cancel from pipeline module."""
        from ora_rd_orchestrator.pipeline import _check_cancel
        return _check_cancel

    def test_none_event_does_nothing(self):
        check = self._get_check_cancel()
        check(None)  # Should not raise

    def test_unset_event_does_nothing(self):
        check = self._get_check_cancel()
        event = threading.Event()
        check(event)  # Should not raise

    def test_set_event_raises(self):
        check = self._get_check_cancel()
        event = threading.Event()
        event.set()
        with pytest.raises(PipelineCancelled):
            check(event)


class TestCancelEventIntegration:
    """Test cancel_event with a thread simulating pipeline work."""

    def test_cancel_stops_thread(self):
        cancel_event = threading.Event()
        result = {"cancelled": False}

        def _worker():
            for _ in range(100):
                if cancel_event.is_set():
                    result["cancelled"] = True
                    return
                threading.Event().wait(0.01)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        cancel_event.set()
        t.join(timeout=5)

        assert not t.is_alive()
        assert result["cancelled"]
