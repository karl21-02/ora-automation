"""Unit tests for config_reader module."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ora_automation_api.config_reader import (
    read_config_file,
    read_json_file,
    read_project_configs,
    read_text_file,
    read_toml_file,
)


class TestReadJsonFile:
    """Test read_json_file function."""

    def test_valid_json(self):
        """Should parse valid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test", "version": "1.0.0"}, f)
            f.flush()

            result = read_json_file(Path(f.name))

        assert result == {"name": "test", "version": "1.0.0"}

    def test_invalid_json(self):
        """Should return None for invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            f.flush()

            result = read_json_file(Path(f.name))

        assert result is None

    def test_nonexistent_file(self):
        """Should return None for nonexistent file."""
        result = read_json_file(Path("/nonexistent/file.json"))
        assert result is None


class TestReadTomlFile:
    """Test read_toml_file function."""

    def test_valid_toml(self):
        """Should parse valid TOML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[project]\nname = "test"\nversion = "1.0.0"\n')
            f.flush()

            result = read_toml_file(Path(f.name))

        assert result == {"project": {"name": "test", "version": "1.0.0"}}

    def test_invalid_toml(self):
        """Should return None for invalid TOML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("[invalid\n")
            f.flush()

            result = read_toml_file(Path(f.name))

        assert result is None


class TestReadTextFile:
    """Test read_text_file function."""

    def test_short_file(self):
        """Should read entire short file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()

            result = read_text_file(Path(f.name))

        assert result == "line1\nline2\nline3"

    def test_truncate_long_file(self):
        """Should truncate long files."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            for i in range(150):
                f.write(f"line{i}\n")
            f.flush()

            result = read_text_file(Path(f.name), max_lines=10)

        lines = result.split("\n")
        assert len(lines) == 11  # 10 + truncation message
        assert "truncated" in lines[-1].lower()


class TestReadConfigFile:
    """Test read_config_file dispatcher."""

    def test_json_type(self):
        """Should dispatch to JSON reader."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()

            result = read_config_file(Path(f.name), "json")

        assert result == {"key": "value"}

    def test_text_type(self):
        """Should dispatch to text reader."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("some text content")
            f.flush()

            result = read_config_file(Path(f.name), "text")

        assert result == "some text content"


class TestReadProjectConfigs:
    """Test read_project_configs function."""

    def test_project_with_configs(self):
        """Should find and parse config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create package.json
            pkg_json = Path(tmpdir) / "package.json"
            pkg_json.write_text('{"name": "test-pkg", "version": "1.0.0"}')

            # Create Makefile
            makefile = Path(tmpdir) / "Makefile"
            makefile.write_text("all:\n\techo hello\n")

            result = read_project_configs(tmpdir)

        assert len(result) == 2

        pkg = next(c for c in result if c["name"] == "package.json")
        assert pkg["type"] == "json"
        assert pkg["content"]["name"] == "test-pkg"

        make = next(c for c in result if c["name"] == "Makefile")
        assert make["type"] == "text"
        assert "echo hello" in make["content"]

    def test_project_without_configs(self):
        """Should return empty list when no config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = read_project_configs(tmpdir)

        assert result == []

    def test_project_with_pyproject(self):
        """Should parse pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject = Path(tmpdir) / "pyproject.toml"
            pyproject.write_text(
                '[project]\nname = "my-project"\nversion = "0.1.0"\n'
            )

            result = read_project_configs(tmpdir)

        assert len(result) == 1
        assert result[0]["name"] == "pyproject.toml"
        assert result[0]["type"] == "toml"
        assert result[0]["content"]["project"]["name"] == "my-project"
