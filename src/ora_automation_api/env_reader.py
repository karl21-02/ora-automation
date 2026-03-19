"""Environment file reader for project .env files."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Keys that should always be masked
SENSITIVE_PATTERNS = {
    "password",
    "secret",
    "key",
    "token",
    "api_key",
    "apikey",
    "private",
    "credential",
    "auth",
}


def mask_value(value: str) -> str:
    """Mask a sensitive value, showing only first and last 2 chars.

    Args:
        value: The value to mask.

    Returns:
        Masked string like "ab••••cd" or "••••" for short values.
    """
    if len(value) <= 4:
        return "••••"
    return value[:2] + "••••" + value[-2:]


def is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates sensitive data.

    Args:
        key: Environment variable key name.

    Returns:
        True if the key likely contains sensitive data.
    """
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_PATTERNS)


def parse_env_file(path: Path, mask_sensitive: bool = True) -> dict[str, str]:
    """Parse a .env file into key-value pairs.

    Args:
        path: Path to the .env file.
        mask_sensitive: If True, mask values for sensitive keys.

    Returns:
        Dict of environment variable key-value pairs.
    """
    if not path.exists():
        return {}

    content: dict[str, str] = {}

    try:
        for line in path.read_text().splitlines():
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Skip lines without =
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Remove surrounding quotes
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            # Mask sensitive values if requested
            if mask_sensitive and is_sensitive_key(key) and value:
                value = mask_value(value)

            content[key] = value

    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read env file %s: %s", path, e)
        return {}

    return content


def read_project_env(project_path: str | Path) -> dict:
    """Read .env and .env.example files from a project.

    Args:
        project_path: Path to the project root directory.

    Returns:
        Dict with has_env, has_env_example, env_content, env_example_content.
    """
    base = Path(project_path)

    result = {
        "has_env": False,
        "has_env_example": False,
        "env_content": {},
        "env_example_content": None,
    }

    # Read .env (with masking)
    env_file = base / ".env"
    if env_file.exists():
        result["has_env"] = True
        result["env_content"] = parse_env_file(env_file, mask_sensitive=True)

    # Read .env.example (no masking - these are example values)
    env_example = base / ".env.example"
    if env_example.exists():
        result["has_env_example"] = True
        result["env_example_content"] = parse_env_file(env_example, mask_sensitive=False)

    return result
