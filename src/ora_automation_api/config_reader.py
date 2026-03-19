"""Config file reader for project configuration files."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Config files to look for, in priority order
CONFIG_FILES = [
    ("package.json", "json"),
    ("pyproject.toml", "toml"),
    ("tsconfig.json", "json"),
    ("go.mod", "text"),
    ("Cargo.toml", "toml"),
    ("Makefile", "text"),
    ("docker-compose.yml", "yaml"),
    ("docker-compose.yaml", "yaml"),
    ("Dockerfile", "text"),
    (".eslintrc.json", "json"),
    (".prettierrc", "json"),
]


def read_json_file(path: Path) -> dict | list | None:
    """Read and parse a JSON file.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed JSON content or None on error.
    """
    try:
        return json.loads(path.read_text())
    except Exception as e:
        logger.warning("Failed to parse JSON file %s: %s", path, e)
        return None


def read_toml_file(path: Path) -> dict | None:
    """Read and parse a TOML file.

    Args:
        path: Path to TOML file.

    Returns:
        Parsed TOML content or None on error.
    """
    try:
        # Python 3.11+ has tomllib built-in
        try:
            import tomllib
        except ImportError:
            # Fallback to tomli for Python 3.10
            import tomli as tomllib
        return tomllib.loads(path.read_text())
    except Exception as e:
        logger.warning("Failed to parse TOML file %s: %s", path, e)
        return None


def read_yaml_file(path: Path) -> dict | list | None:
    """Read and parse a YAML file.

    Args:
        path: Path to YAML file.

    Returns:
        Parsed YAML content or None on error.
    """
    try:
        import yaml
        return yaml.safe_load(path.read_text())
    except Exception as e:
        logger.warning("Failed to parse YAML file %s: %s", path, e)
        return None


def read_text_file(path: Path, max_lines: int = 100) -> str:
    """Read a text file, truncating if too long.

    Args:
        path: Path to text file.
        max_lines: Maximum number of lines to return.

    Returns:
        File content as string, truncated if necessary.
    """
    try:
        lines = path.read_text().splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append(f"... (truncated, {len(lines)} more lines)")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("Failed to read text file %s: %s", path, e)
        return ""


def read_config_file(path: Path, file_type: str) -> dict | list | str | None:
    """Read and parse a config file based on its type.

    Args:
        path: Path to config file.
        file_type: Type of file (json, toml, yaml, text).

    Returns:
        Parsed content or None on error.
    """
    if file_type == "json":
        return read_json_file(path)
    elif file_type == "toml":
        return read_toml_file(path)
    elif file_type == "yaml":
        return read_yaml_file(path)
    else:
        return read_text_file(path)


def read_project_configs(project_path: str | Path) -> list[dict]:
    """Read all config files from a project.

    Args:
        project_path: Path to the project root directory.

    Returns:
        List of config file dicts with name, path, type, content.
    """
    base = Path(project_path)
    configs: list[dict] = []

    for filename, file_type in CONFIG_FILES:
        filepath = base / filename
        if not filepath.exists():
            continue

        content = read_config_file(filepath, file_type)
        if content is None:
            continue

        configs.append({
            "name": filename,
            "path": str(filepath),
            "type": file_type,
            "content": content,
        })

    return configs
