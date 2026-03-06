"""Tests for path traversal protection in report download endpoint."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestGetReportPathTraversal:
    """Verify that the /reports/{filename} endpoint blocks path traversal."""

    def test_dotdot_in_filename_blocked(self, client, tmp_path):
        """filename containing '..' is rejected even if not a real traversal."""
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        with patch(
            "ora_automation_api.chat_router._report_dirs",
            return_value=[report_dir],
        ):
            resp = client.get("/api/v1/reports/..%2Fsecret.md")
            assert resp.status_code in (400, 404)

    def test_encoded_dotdot_blocked(self, client):
        resp = client.get("/api/v1/reports/%2e%2e/%2e%2e/etc/passwd")
        assert resp.status_code in (400, 404)

    def test_absolute_path_blocked(self, client):
        resp = client.get("/api/v1/reports//etc/passwd")
        assert resp.status_code in (400, 404)

    def test_valid_filename_not_found(self, client):
        resp = client.get("/api/v1/reports/nonexistent.md")
        assert resp.status_code == 404

    def test_valid_report_served(self, client, tmp_path):
        """A legitimate .md file inside the report dir is served."""
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        (report_dir / "test-report.md").write_text("# Test Report")

        with patch(
            "ora_automation_api.chat_router._report_dirs",
            return_value=[report_dir],
        ):
            resp = client.get("/api/v1/reports/test-report.md")
            assert resp.status_code == 200
            assert "# Test Report" in resp.text

    def test_symlink_outside_base_blocked(self, client, tmp_path):
        """Symlink pointing outside base dir should be blocked."""
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret.md"
        secret.write_text("SECRET")
        link = report_dir / "evil.md"
        link.symlink_to(secret)

        with patch(
            "ora_automation_api.chat_router._report_dirs",
            return_value=[report_dir],
        ):
            resp = client.get("/api/v1/reports/evil.md")
            assert resp.status_code == 400

    def test_non_allowed_extension_blocked(self, client, tmp_path):
        """Only .md and .json are served."""
        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        (report_dir / "script.sh").write_text("#!/bin/bash\nrm -rf /")

        with patch(
            "ora_automation_api.chat_router._report_dirs",
            return_value=[report_dir],
        ):
            resp = client.get("/api/v1/reports/script.sh")
            assert resp.status_code == 404
