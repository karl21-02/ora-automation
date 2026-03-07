"""Persona registry: load agent personas from YAML files."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import default_persona_dir
from .types import AgentPersona

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YAML loader (lazy import to keep pyyaml optional at import time)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "pyyaml is required for persona loading. "
            "Install it with: pip install 'pyyaml>=6.0.1,<7.0.0'"
        ) from exc
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt(data: dict[str, Any]) -> str:
    """Render the system_prompt_template with persona fields."""
    template = data.get("system_prompt_template", "")
    if not template:
        return ""

    personality = data.get("personality", {})

    # Format behavioral directives as numbered list
    directives = data.get("behavioral_directives", [])
    directives_formatted = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(directives))

    # Format constraints as numbered list
    constraints = data.get("constraints", [])
    constraints_formatted = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(constraints))

    # Simple placeholder replacement
    prompt = template
    replacements = {
        "{display_name_ko}": data.get("display_name_ko", data.get("display_name", "")),
        "{display_name}": data.get("display_name", ""),
        "{personality.archetype}": personality.get("archetype", ""),
        "{personality.motivation}": personality.get("motivation", ""),
        "{personality.communication_style}": personality.get("communication_style", ""),
        "{behavioral_directives_formatted}": directives_formatted,
        "{constraints_formatted}": constraints_formatted,
        "{team}": data.get("team", ""),
        "{domain}": str(data.get("domain", "")),
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)

    return prompt.strip()


# ---------------------------------------------------------------------------
# Persona parsing
# ---------------------------------------------------------------------------

def _parse_persona(data: dict[str, Any], source_path: Path | None = None) -> AgentPersona:
    """Parse a raw YAML dict into an AgentPersona dataclass."""
    agent_id = data.get("agent_id", "")
    if not agent_id:
        raise ValueError(f"Missing 'agent_id' in persona file {source_path}")

    return AgentPersona(
        agent_id=agent_id,
        display_name=data.get("display_name", agent_id),
        display_name_ko=data.get("display_name_ko", data.get("display_name", agent_id)),
        role=data.get("role", ""),
        tier=int(data.get("tier", 1)),
        domain=data.get("domain") or None,
        team=data.get("team", ""),
        system_prompt=_build_system_prompt(data),
        behavioral_directives=data.get("behavioral_directives", []),
        constraints=data.get("constraints", []),
        decision_focus=data.get("decision_focus", []),
        trust_map=data.get("trust_map", {}),
        weights=data.get("weights", {}),
    )


# ---------------------------------------------------------------------------
# PersonaRegistry
# ---------------------------------------------------------------------------

def _merge_chapter_into_agent(agent: dict[str, Any], chapter: dict[str, Any]) -> dict[str, Any]:
    """Merge chapter shared knowledge into agent dict (copy, non-mutating)."""
    merged = {**agent}
    merged["behavioral_directives"] = (
        (chapter.get("shared_directives") or []) + (agent.get("behavioral_directives") or [])
    )
    merged["constraints"] = (
        (chapter.get("shared_constraints") or []) + (agent.get("constraints") or [])
    )
    merged["decision_focus"] = (
        (chapter.get("shared_decision_focus") or []) + (agent.get("decision_focus") or [])
    )
    chapter_prompt = (chapter.get("chapter_prompt") or "").strip()
    if chapter_prompt:
        orig = (agent.get("system_prompt_template") or "").strip()
        merged["system_prompt_template"] = chapter_prompt + "\n\n" + orig if orig else chapter_prompt
    return merged


class PersonaRegistry:
    """Registry that loads and provides access to agent personas from YAML files."""

    def __init__(self, persona_dir: Path | None = None) -> None:
        self._persona_dir = persona_dir or default_persona_dir()
        self._personas: dict[str, AgentPersona] = {}
        self._loaded = False

    @classmethod
    def from_agent_dicts(cls, agents: list[dict[str, Any]]) -> "PersonaRegistry":
        """Create a PersonaRegistry from a list of agent config dicts (DB rows).

        Each dict should contain the same keys as a YAML persona file:
        agent_id, display_name, display_name_ko, role, tier, domain, team,
        personality, behavioral_directives, constraints, decision_focus,
        weights, trust_map, system_prompt_template.
        """
        registry = cls.__new__(cls)
        registry._persona_dir = Path("/dev/null")
        registry._personas = {}
        registry._loaded = True

        for agent_data in agents:
            if not agent_data.get("agent_id"):
                continue
            if not agent_data.get("enabled", True):
                continue
            try:
                persona = _parse_persona(agent_data)
                registry._personas[persona.agent_id] = persona
            except Exception:
                logger.exception(
                    "Failed to parse agent dict for %s",
                    agent_data.get("agent_id", "unknown"),
                )

        logger.info("Created PersonaRegistry from %d agent dicts", len(registry._personas))
        return registry

    @classmethod
    def from_org_config(cls, org_config: dict[str, Any]) -> "PersonaRegistry":
        """Create registry from org_config with chapter prompt merging."""
        chapter_map = {c["id"]: c for c in org_config.get("chapters", [])}

        merged_agents: list[dict[str, Any]] = []
        for agent in org_config.get("agents", []):
            if not agent.get("enabled", True):
                continue
            chapter = chapter_map.get(agent.get("chapter_id"))
            if chapter:
                merged = _merge_chapter_into_agent(agent, chapter)
            else:
                merged = agent
            merged_agents.append(merged)

        registry = cls.__new__(cls)
        registry._persona_dir = Path("/dev/null")
        registry._personas = {}
        registry._loaded = True
        for agent_data in merged_agents:
            if not agent_data.get("agent_id"):
                continue
            try:
                persona = _parse_persona(agent_data)
                registry._personas[persona.agent_id] = persona
            except Exception:
                logger.exception(
                    "Failed to parse agent dict for %s",
                    agent_data.get("agent_id", "unknown"),
                )

        logger.info("Created PersonaRegistry from org_config with %d personas", len(registry._personas))
        return registry

    # -- Loading --------------------------------------------------------

    def load_all(self) -> dict[str, AgentPersona]:
        """Load all persona YAML files from the persona directory.

        Returns the internal persona dict (keyed by agent_id).
        """
        self._personas.clear()

        if not self._persona_dir.is_dir():
            logger.warning("Persona directory not found: %s", self._persona_dir)
            self._loaded = True
            return self._personas

        yaml_files = sorted(self._persona_dir.glob("*.yaml")) + sorted(self._persona_dir.glob("*.yml"))
        for yaml_path in yaml_files:
            try:
                data = _load_yaml(yaml_path)
                persona = _parse_persona(data, source_path=yaml_path)
                self._personas[persona.agent_id] = persona
            except Exception:
                logger.exception("Failed to load persona from %s", yaml_path)

        self._loaded = True
        logger.info("Loaded %d personas from %s", len(self._personas), self._persona_dir)
        return self._personas

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load_all()

    # -- Accessors ------------------------------------------------------

    def get_persona(self, agent_id: str) -> AgentPersona | None:
        """Return persona for the given agent_id, or None if not found."""
        self._ensure_loaded()
        return self._personas.get(agent_id)

    def get_team(self, team_name: str) -> list[AgentPersona]:
        """Return all personas belonging to a team/silo."""
        self._ensure_loaded()
        return [p for p in self._personas.values() if p.team == team_name]

    def get_tier(self, tier: int) -> list[AgentPersona]:
        """Return all personas at a given tier level."""
        self._ensure_loaded()
        return [p for p in self._personas.values() if p.tier == tier]

    def get_system_prompt(self, agent_id: str) -> str:
        """Return the rendered system prompt for an agent, or empty string."""
        persona = self.get_persona(agent_id)
        if persona is None:
            return ""
        return persona.system_prompt

    def all_agent_ids(self) -> list[str]:
        """Return sorted list of all loaded agent IDs."""
        self._ensure_loaded()
        return sorted(self._personas.keys())

    # -- Backward compatibility -----------------------------------------

    def to_agent_definitions(self) -> dict[str, dict[str, object]]:
        """Convert loaded personas to the legacy AGENT_DEFINITIONS format.

        This allows gradual migration — code that reads AGENT_DEFINITIONS
        can instead call ``registry.to_agent_definitions()``.
        """
        self._ensure_loaded()
        definitions: dict[str, dict[str, object]] = {}
        for agent_id, persona in self._personas.items():
            definitions[agent_id] = {
                "objective": persona.display_name_ko,
                "weights": dict(persona.weights),
                "trust": dict(persona.trust_map),
                "decision_focus": list(persona.decision_focus),
                "tier": persona.tier,
                "domain": persona.domain,
                # No support/challenge rule functions — LLM handles this now
                "supports": [],
                "challenges": [],
            }
        return definitions

    def to_agent_weights(self) -> dict[str, dict[str, float]]:
        """Return {agent_id: weights_dict} for all loaded personas."""
        self._ensure_loaded()
        return {
            agent_id: dict(persona.weights)
            for agent_id, persona in self._personas.items()
        }

    def to_trust_map(self) -> dict[str, dict[str, float]]:
        """Return {agent_id: trust_dict} for all loaded personas."""
        self._ensure_loaded()
        return {
            agent_id: dict(persona.trust_map)
            for agent_id, persona in self._personas.items()
        }

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._personas)

    def __contains__(self, agent_id: str) -> bool:
        self._ensure_loaded()
        return agent_id in self._personas

    def __iter__(self):
        self._ensure_loaded()
        return iter(self._personas.values())
