"""Unit tests for env_reader module."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ora_automation_api.env_reader import (
    is_sensitive_key,
    mask_value,
    parse_env_file,
    read_project_env,
)


class TestMaskValue:
    """Test mask_value function."""

    def test_short_value(self):
        """Should mask short values completely."""
        assert mask_value("abc") == "••••"
        assert mask_value("1234") == "••••"
        assert mask_value("") == "••••"

    def test_long_value(self):
        """Should show first and last 2 chars."""
        assert mask_value("12345") == "12••••45"
        assert mask_value("abcdefghij") == "ab••••ij"
        assert mask_value("secret_key_12345") == "se••••45"


class TestIsSensitiveKey:
    """Test is_sensitive_key function."""

    def test_sensitive_keys(self):
        """Should detect sensitive key patterns."""
        assert is_sensitive_key("PASSWORD") is True
        assert is_sensitive_key("db_password") is True
        assert is_sensitive_key("API_KEY") is True
        assert is_sensitive_key("api_key") is True
        assert is_sensitive_key("SECRET") is True
        assert is_sensitive_key("jwt_secret") is True
        assert is_sensitive_key("PRIVATE_KEY") is True
        assert is_sensitive_key("auth_token") is True
        assert is_sensitive_key("CREDENTIAL") is True

    def test_non_sensitive_keys(self):
        """Should not flag non-sensitive keys."""
        assert is_sensitive_key("DATABASE_URL") is False
        assert is_sensitive_key("PORT") is False
        assert is_sensitive_key("NODE_ENV") is False
        assert is_sensitive_key("DEBUG") is False
        assert is_sensitive_key("LOG_LEVEL") is False


class TestParseEnvFile:
    """Test parse_env_file function."""

    def test_parse_simple_env(self):
        """Should parse simple key=value pairs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("FOO=bar\n")
            f.write("BAZ=qux\n")
            f.flush()

            result = parse_env_file(Path(f.name), mask_sensitive=False)

        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_parse_with_comments(self):
        """Should skip comments and empty lines."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# This is a comment\n")
            f.write("\n")
            f.write("KEY=value\n")
            f.write("  # Another comment\n")
            f.flush()

            result = parse_env_file(Path(f.name), mask_sensitive=False)

        assert result == {"KEY": "value"}

    def test_parse_with_quotes(self):
        """Should remove surrounding quotes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('DOUBLE="hello world"\n')
            f.write("SINGLE='single quoted'\n")
            f.write("NONE=no quotes\n")
            f.flush()

            result = parse_env_file(Path(f.name), mask_sensitive=False)

        assert result["DOUBLE"] == "hello world"
        assert result["SINGLE"] == "single quoted"
        assert result["NONE"] == "no quotes"

    def test_mask_sensitive_values(self):
        """Should mask sensitive values when requested."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("DATABASE_URL=postgres://localhost\n")
            f.write("API_KEY=supersecretkey123\n")
            f.write("PASSWORD=mypassword\n")
            f.flush()

            result = parse_env_file(Path(f.name), mask_sensitive=True)

        assert result["DATABASE_URL"] == "postgres://localhost"  # Not sensitive
        assert result["API_KEY"] == "su••••23"  # Masked
        assert result["PASSWORD"] == "my••••rd"  # Masked

    def test_nonexistent_file(self):
        """Should return empty dict for nonexistent file."""
        result = parse_env_file(Path("/nonexistent/path/.env"))
        assert result == {}


class TestReadProjectEnv:
    """Test read_project_env function."""

    def test_project_with_env_only(self):
        """Should read .env when only it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("FOO=bar\nSECRET=hidden123\n")

            result = read_project_env(tmpdir)

        assert result["has_env"] is True
        assert result["has_env_example"] is False
        assert result["env_content"]["FOO"] == "bar"
        assert result["env_content"]["SECRET"] == "hi••••23"  # Masked
        assert result["env_example_content"] is None

    def test_project_with_both_files(self):
        """Should read both .env and .env.example."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("API_KEY=real_secret_key\n")

            example_file = Path(tmpdir) / ".env.example"
            example_file.write_text("API_KEY=your_api_key_here\n")

            result = read_project_env(tmpdir)

        assert result["has_env"] is True
        assert result["has_env_example"] is True
        assert result["env_content"]["API_KEY"] == "re••••ey"  # Masked
        assert result["env_example_content"]["API_KEY"] == "your_api_key_here"  # Not masked

    def test_project_without_env(self):
        """Should handle project without .env files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = read_project_env(tmpdir)

        assert result["has_env"] is False
        assert result["has_env_example"] is False
        assert result["env_content"] == {}
        assert result["env_example_content"] is None
