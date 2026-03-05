"""Main orchestration pipeline for R&D report generation.

Replaces the monolithic ``generate_report()`` in engine.py with a modular
pipeline that delegates to extracted modules:

    personas → workspace → topic_discovery → scoring → deliberation → consensus → research → report_builder

All scoring, deliberation, consensus, strategy card, QA, and phase plan
generation use LLM calls. Flat mode requires LLM commands.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .config import (
    AGENT_FINAL_WEIGHTS,
    DEBATE_ROUNDS_DEFAULT,
    FLAT_MODE_AGENTS,
    HIERARCHICAL_FINAL_WEIGHTS,
    HIERARCHICAL_TRUST,
    LLM_CONSENSUS_CMD_ENV,
    LLM_CONSENSUS_TIMEOUT_SECONDS,
    LLM_DELIBERATION_CMD_ENV,
    LLM_DELIBERATION_TIMEOUT_SECONDS,
    LLM_REPORT_SECTION_CMD_ENV,
    LLM_REPORT_SECTION_TIMEOUT_SECONDS,
    LLM_SCORING_CMD_ENV,
    LLM_TOPIC_DISCOVERY_CMD_ENV,
    ORCHESTRATION_PROFILE_DEFAULT,
    ORCHESTRATION_PROFILE_LABELS,
    ORCHESTRATION_PROFILE_STRICT,
    ORCHESTRATION_STAGE_ANALYSIS,
    ORCHESTRATION_STAGE_DELIBERATION,
    ORCHESTRATION_STAGE_EXECUTION,
    ORCHESTRATION_STAGES_DEFAULT,
    PERSONA_DIR_ENV,
    PIPELINE_FAIL_LABEL_RETRY,
    PIPELINE_FAIL_LABEL_SKIP,
    PIPELINE_FAIL_LABEL_STOP,
    QA_GATE_THRESHOLD_DEFAULT,
    SUBORDINATE_BLEND_DEFAULT,
    TIER_2_DOMAIN_MAP,
    _build_service_scope,
    _normalize_stages,
    _parse_service_scope_tokens,
)
from .consensus import apply_hybrid_consensus
from .deliberation import llm_deliberation_round
from .personas import PersonaRegistry, default_persona_dir
from .report_builder import (
    _agent_score_key,
    _clamp_score,
    as_markdown,
    build_agent_rankings,
    build_final_score,
    build_phase_plan_via_llm,
    build_synergy_graph,
    generate_asis_analysis_via_llm,
    generate_executive_summary_via_llm,
    generate_feasibility_evidence_via_llm,
    generate_strategy_cards_via_llm,
    generate_tobe_direction_via_llm,
    run_qa_verification_via_llm,
    to_json,
)
from .research import build_research_queries, build_sources_file
from .scoring import score_all_agents
from .topic_discovery import discover_topics, topics_to_dict, topics_to_keywords
from .types import (
    CheckpointCallback,
    CheckpointData,
    CheckpointResponse,
    HierarchicalPipelineState,
    OrchestrationDecision,
    TierResult,
    TopicState,
)
from .workspace import analyze_workspace, collect_workspace_summary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline decisions helper
# ---------------------------------------------------------------------------

def _pipeline_decisions_to_topic_records(
    decisions: list[OrchestrationDecision] | None,
    agent_definitions: dict[str, dict] | None = None,
) -> dict[str, list[dict]]:
    """Convert pipeline decisions to per-topic record dicts."""
    _defs = agent_definitions or {}
    records: dict[str, list[dict]] = {}
    for item in decisions or []:
        record = {
            "agent": item.owner,
            "objective": _defs.get(item.owner, {}).get("objective", ""),
            "decision": "review",
            "reason": item.rationale,
            "focus": _defs.get(item.owner, {}).get("decision_focus", []),
            "score": item.confidence,
            "risk": item.risk,
            "next_action": item.next_action,
            "fail_label": item.fail_label,
            "due": item.due,
            "service": item.service,
        }
        records.setdefault(item.topic_id, []).append(record)
    return records


def _best_owner_from_scores(topic_scores: dict[str, float]) -> str:
    best_owner = "Planner"
    best_score = -1.0
    for key, value in topic_scores.items():
        if not key.startswith("score_"):
            continue
        try:
            score_value = float(value)
        except Exception:
            continue
        if score_value > best_score:
            best_score = score_value
            best_owner = key.replace("score_", "", 1) or "Planner"
    return best_owner


def _build_fallback_decisions_via_llm(
    selected: list[dict[str, Any]],
    scores: dict[str, dict[str, float]],
    service_scope: list[str],
    llm_command: str | None = None,
    llm_timeout: float = 15.0,
) -> list[OrchestrationDecision]:
    """Generate fallback decisions via LLM when deliberation has no decisions."""
    from .llm_client import run_llm_command as _run_llm

    payload = {
        "version": "llm-fallback-decisions-v1",
        "system_prompt": (
            "You are a research orchestrator. The LLM deliberation rounds did not produce decisions. "
            "Given the ranked topics with scores and features, generate one decision per topic.\n\n"
            "For each topic, determine:\n"
            "- owner: which agent role best fits (e.g. Researcher, Developer, PM, Planner)\n"
            "- rationale: brief explanation of why this topic matters\n"
            "- risk: low/medium/high based on features\n"
            "- next_action: concrete next step\n"
            "- fail_label: SKIP (safe to skip), RETRY (worth retrying), or STOP (critical risk)\n"
            "- confidence: 0.0~1.0\n\n"
            "Return JSON: {\"decisions\": [{\"topic_id\": \"...\", \"owner\": \"...\", "
            "\"rationale\": \"...\", \"risk\": \"low|medium|high\", \"next_action\": \"...\", "
            "\"fail_label\": \"SKIP|RETRY|STOP\", \"confidence\": 0.7}]}"
        ),
        "topics": [
            {
                "topic_id": item.get("topic_id"),
                "topic_name": item.get("topic_name"),
                "total_score": item.get("total_score", 0),
                "features": item.get("features", {}),
                "scores": scores.get(str(item.get("topic_id", "")), {}),
            }
            for item in selected
        ],
        "service_scope": service_scope,
    }

    decisions: list[OrchestrationDecision] = []

    if llm_command:
        result = _run_llm(payload=payload, command=llm_command, timeout=llm_timeout)
        if result.status == "ok":
            items = result.parsed.get("decisions", [])
            if isinstance(items, list):
                from .deliberation import parse_llm_decision_record
                topic_catalog = {}
                for item in selected:
                    tid = str(item.get("topic_id", "")).strip()
                    if tid:
                        # Create a minimal TopicState for the parser
                        topic_catalog[tid] = type("_T", (), {"topic_name": item.get("topic_name", tid)})()
                for d in items:
                    if not isinstance(d, dict):
                        continue
                    parsed = parse_llm_decision_record(d, topic_catalog, service_scope)
                    if parsed.topic_id not in [x.topic_id for x in decisions]:
                        decisions.append(parsed)
                if decisions:
                    return decisions

    # Minimal fallback — just use score ranking to assign basic decisions (no threshold rules)
    due = (dt.datetime.now() + dt.timedelta(days=14)).strftime("%Y-%m-%d")
    for item in selected:
        topic_id = str(item.get("topic_id", "")).strip()
        if not topic_id:
            continue
        topic_name = str(item.get("topic_name", topic_id)).strip() or topic_id
        owner = _best_owner_from_scores(scores.get(topic_id, {}))
        consensus_score = float(item.get("total_score", 0) or 0)
        confidence = round(max(0.0, min(1.0, consensus_score / 10.0)), 4)
        decisions.append(
            OrchestrationDecision(
                decision_id=f"fallback-{uuid.uuid4().hex[:10]}",
                owner=owner,
                rationale="LLM deliberation 미결정 — 스코어 랭킹 기반 자동 생성",
                risk="medium",
                next_action="PoC 범위 확정 후 스프린트 목표 설정",
                due=due,
                topic_id=topic_id,
                topic_name=topic_name,
                service=service_scope,
                score_delta=0.0,
                confidence=confidence,
                fail_label=PIPELINE_FAIL_LABEL_RETRY,
            )
        )
    return decisions


# ---------------------------------------------------------------------------
# Hierarchical pipeline (delegates to engine.py until fully extracted)
# ---------------------------------------------------------------------------

def _run_hierarchical_pipeline_legacy(
    states: dict[str, TopicState],
    tier3_debate_rounds: int = 2,
    subordinate_blend: float = SUBORDINATE_BLEND_DEFAULT,
    qa_gate_threshold: float = QA_GATE_THRESHOLD_DEFAULT,
) -> HierarchicalPipelineState:
    """Run the 4-tier hierarchical pipeline.

    Imports from engine.py to reuse the existing tier execution functions
    that haven't been fully extracted yet.
    """
    from .engine import _run_hierarchical_pipeline  # type: ignore[attr-defined]

    return _run_hierarchical_pipeline(
        states=states,
        tier3_debate_rounds=tier3_debate_rounds,
        subordinate_blend=subordinate_blend,
        qa_gate_threshold=qa_gate_threshold,
    )


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def generate_report(
    workspace: Path,
    top_k: int,
    output_dir: Path,
    output_name: str,
    max_files: int,
    extensions: List[str],
    ignore_dirs: set[str],
    history_files: list[Path],
    report_focus: str = "",
    version_tag: str = "V10",
    debate_rounds: int = DEBATE_ROUNDS_DEFAULT,
    orchestration_profile: str = ORCHESTRATION_PROFILE_DEFAULT,
    orchestration_stages: list[str] | str | None = None,
    service_scope: list[str] | str | None = None,
    feature_scope: list[str] | str | None = None,
    llm_deliberation_cmd: str | None = None,
    llm_deliberation_timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
    llm_consensus_cmd: str | None = None,
    llm_consensus_timeout: float = LLM_CONSENSUS_TIMEOUT_SECONDS,
    agent_mode: str = "flat",
    tier3_debate_rounds: int = 2,
    qa_gate_threshold: float = QA_GATE_THRESHOLD_DEFAULT,
    subordinate_blend: float = SUBORDINATE_BLEND_DEFAULT,
    # --- new parameters ---
    persona_dir: Path | str | None = None,
    llm_topic_discovery_cmd: str | None = None,
    llm_scoring_cmd: str | None = None,
    llm_scoring_timeout: float = 10.0,
    checkpoint: CheckpointCallback = None,
) -> dict:
    """Generate an R&D strategy report.

    This is the main orchestration entry point. It coordinates:

    1. Persona loading (``personas.py``)
    2. Workspace summary collection (``workspace.py``)
    3. Topic discovery via LLM or legacy fallback (``topic_discovery.py``)
    4. Workspace analysis with discovered topics (``workspace.py``)
    5. Agent scoring via LLM or legacy fallback (``scoring.py``)
    6. Multi-round LLM deliberation (``deliberation.py``)
    7. Final consensus (``consensus.py``)
    8. Research query generation (``research.py``)
    9. Markdown + JSON report output (``report_builder.py``)

    Parameters match the original ``engine.generate_report()`` signature
    with additional parameters for LLM-driven features.
    """
    # ------------------------------------------------------------------
    # 0. Normalize inputs
    # ------------------------------------------------------------------
    agent_mode = (agent_mode or "flat").strip().lower()
    if agent_mode not in ("flat", "hierarchical"):
        agent_mode = "flat"

    profile = (orchestration_profile or ORCHESTRATION_PROFILE_DEFAULT).strip().lower()
    if profile not in ORCHESTRATION_PROFILE_LABELS:
        profile = ORCHESTRATION_PROFILE_DEFAULT

    stages = _normalize_stages(
        orchestration_stages if orchestration_stages is not None else ORCHESTRATION_STAGES_DEFAULT,
        fallback=ORCHESTRATION_STAGES_DEFAULT,
    )
    service_scope_tokens = _parse_service_scope_tokens(service_scope)
    service_scope_list = _build_service_scope(service_scope_tokens)

    if isinstance(feature_scope, str):
        feature_scope_list = [token.strip() for token in feature_scope.split(",") if token.strip()]
    else:
        feature_scope_list = [str(token).strip() for token in (feature_scope or []) if str(token).strip()]

    stage_log: list[dict] = []
    pipeline_decisions: list[OrchestrationDecision] = []

    # ------------------------------------------------------------------
    # 1. Load personas
    # ------------------------------------------------------------------
    resolved_persona_dir = persona_dir
    if not resolved_persona_dir:
        env_dir = os.getenv(PERSONA_DIR_ENV, "").strip()
        resolved_persona_dir = Path(env_dir) if env_dir else default_persona_dir()
    else:
        resolved_persona_dir = Path(resolved_persona_dir)

    registry = PersonaRegistry(resolved_persona_dir)
    personas = registry.load_all()
    agent_definitions = registry.to_agent_definitions() if personas else None
    topic_keywords: dict[str, list[str]] | None = None

    logger.info("Loaded %d personas from %s", len(personas), resolved_persona_dir)

    # ------------------------------------------------------------------
    # 2. Workspace summary + Topic discovery
    # ------------------------------------------------------------------
    resolved_topic_cmd = llm_topic_discovery_cmd
    if not resolved_topic_cmd:
        resolved_topic_cmd = os.getenv(LLM_TOPIC_DISCOVERY_CMD_ENV, "").strip() or None

    # Always collect workspace summary — needed for dynamic topic discovery
    workspace_summary = collect_workspace_summary(
        workspace=workspace,
        extensions=set(extensions),
        ignore_dirs=ignore_dirs,
        max_files=min(max_files, 500),
    )

    # Use report_focus as domain hint when provided (e.g. "OraB2bAndroid"),
    # otherwise default to "voice AI"
    discovery_domain = report_focus.strip() if report_focus and report_focus.strip() else "voice AI"

    discoveries = discover_topics(
        workspace_summary=workspace_summary,
        llm_command=resolved_topic_cmd,
        domain=discovery_domain,
    )
    topics_dict = topics_to_dict(discoveries)
    topic_keywords = topics_to_keywords(discoveries)

    logger.info("Discovered %d topics (source: %s)",
                len(discoveries),
                discoveries[0].discovered_by if discoveries else "none")

    # ------------------------------------------------------------------
    # 2.5 Interactive checkpoint: let user review discovered topics
    # ------------------------------------------------------------------
    if checkpoint is not None:
        topic_items = [
            {
                "topic_id": td.topic_id,
                "topic_name": td.topic_name,
                "confidence": td.confidence,
                "discovered_by": td.discovered_by,
                "keywords_preview": td.suggested_keywords[:5],
            }
            for td in discoveries
        ]
        cp_data = CheckpointData(
            stage="topic_discovery",
            message=f"{len(discoveries)}개 토픽이 발견되었습니다. 이 토픽들로 진행할까요?",
            items=topic_items,
            metadata={"domain": discovery_domain},
        )
        cp_response = checkpoint(cp_data)
        if not cp_response.approved:
            return {
                "status": "cancelled",
                "stage": "topic_discovery",
                "message": cp_response.feedback or "사용자가 토픽 검토 단계에서 취소했습니다.",
                "discovered_topics": topic_items,
            }
        # User may have modified the topic list
        if cp_response.modified_items is not None:
            from .topic_discovery import _load_seed_json
            # Rebuild discoveries from user-modified items
            modified_discoveries = []
            for item in cp_response.modified_items:
                if not isinstance(item, dict):
                    continue
                from .types import TopicDiscovery as _TD
                modified_discoveries.append(_TD(
                    topic_id=item.get("topic_id", ""),
                    topic_name=item.get("topic_name", ""),
                    description=item.get("description", ""),
                    suggested_keywords=item.get("suggested_keywords", item.get("keywords_preview", [])),
                    confidence=float(item.get("confidence", 0.5)),
                    discovered_by="user_modified",
                ))
            if modified_discoveries:
                discoveries = modified_discoveries
                topics_dict = topics_to_dict(discoveries)
                topic_keywords = topics_to_keywords(discoveries)
                logger.info("User modified topics: %d topics after checkpoint", len(discoveries))

    # ------------------------------------------------------------------
    # 3. Workspace analysis
    # ------------------------------------------------------------------
    stage_log.append({
        "stage": ORCHESTRATION_STAGE_ANALYSIS,
        "status": "started",
        "message": f"workspace scan start (service_scope={','.join(service_scope_list)})",
    })

    states = analyze_workspace(
        workspace=workspace,
        extensions=extensions,
        ignore_dirs=ignore_dirs,
        max_files=max_files,
        history_files=history_files,
        service_scope=service_scope_tokens,
        topic_discoveries=discoveries,
    )

    stage_log.append({
        "stage": ORCHESTRATION_STAGE_ANALYSIS,
        "status": "completed",
        "message": f"topic_count={len(states)}",
    })

    # ------------------------------------------------------------------
    # HIERARCHICAL MODE
    # ------------------------------------------------------------------
    if agent_mode == "hierarchical":
        stage_log.append({
            "stage": "hierarchical_pipeline",
            "status": "started",
            "message": f"agent_mode=hierarchical tier3_rounds={tier3_debate_rounds}",
        })

        h_pipeline = _run_hierarchical_pipeline_legacy(
            states=states,
            tier3_debate_rounds=max(0, tier3_debate_rounds),
            subordinate_blend=subordinate_blend,
            qa_gate_threshold=qa_gate_threshold,
        )
        ranked = h_pipeline.final_ranking

        stage_log.append({
            "stage": "hierarchical_pipeline",
            "status": "completed",
            "message": f"tiers=4, topics={len(ranked)}",
        })

        selected = ranked[:top_k]
        _phase_llm_cmd = llm_deliberation_command or llm_consensus_cmd
        phases = build_phase_plan_via_llm(selected, top_k=top_k, llm_command=_phase_llm_cmd)
        synergy = build_synergy_graph(states, selected)

        # Build flat-compatible scores dict from hierarchical results
        scores: dict[str, dict[str, float]] = {}
        for topic_id in states:
            per_topic: dict[str, float] = {}
            for tier_num in (1, 2, 3, 4):
                tr = h_pipeline.tier_results.get(tier_num)
                if tr:
                    for ak, av in tr.agent_scores.get(topic_id, {}).items():
                        per_topic[ak] = av
            scores[topic_id] = per_topic

        agent_rankings = build_agent_rankings(scores, top_k=top_k)

        queries = build_research_queries(selected, topic_keywords=topic_keywords, top_k=min(6, top_k))
        output_dir.mkdir(parents=True, exist_ok=True)
        research_sources, _search_warnings = build_sources_file(
            output_dir=output_dir,
            version_tag=version_tag,
            report_focus=report_focus,
            top_topics=selected,
            topic_keywords=topic_keywords,
        )
        if _search_warnings:
            stage_log.append({
                "stage": "research_search",
                "status": "partial",
                "message": f"search_warnings={len(_search_warnings)} (some APIs failed)",
                "warnings": [
                    {"provider": w.get("provider", ""), "topic": w.get("topic", ""), "error": w.get("search_error", "")}
                    for w in _search_warnings[:10]
                ],
            })

        # Derive tier agent sets from personas if available
        tier1_agents = registry.get_tier(1) if personas else []
        tier1_agent_names = [p.agent_id for p in tier1_agents] if tier1_agents else []

        hierarchical_analysis = {
            "mode": "hierarchical",
            "tier1": {
                "agents": tier1_agent_names or list(h_pipeline.tier_results.get(1, TierResult()).agent_scores.keys()),
                "scores": h_pipeline.tier_results[1].agent_scores if 1 in h_pipeline.tier_results else {},
            },
            "tier2": {
                "leads": list(TIER_2_DOMAIN_MAP.keys()),
                "scores": h_pipeline.tier_results[2].agent_scores if 2 in h_pipeline.tier_results else {},
                "flags": h_pipeline.tier_results[2].flags if 2 in h_pipeline.tier_results else {},
                "subordinate_blend": subordinate_blend,
            },
            "tier3": {
                "debate_rounds": tier3_debate_rounds,
                "scores": h_pipeline.tier_results[3].agent_scores if 3 in h_pipeline.tier_results else {},
                "debate_log": (h_pipeline.tier_results[3].debate_log or []) if 3 in h_pipeline.tier_results else [],
                "flags": h_pipeline.tier_results[3].flags if 3 in h_pipeline.tier_results else {},
            },
            "tier4": {
                "scores": h_pipeline.tier_results[4].agent_scores if 4 in h_pipeline.tier_results else {},
                "qa_penalty_topics": (
                    h_pipeline.tier_results[4].metadata.get("qa_penalty_applied", [])
                    if 4 in h_pipeline.tier_results
                    else []
                ),
            },
            "execution_log": h_pipeline.execution_log,
        }

        # LLM report sections (As-Is → To-Be → Feasibility → Executive Summary)
        _h_report_cmd = (
            os.getenv(LLM_REPORT_SECTION_CMD_ENV, "").strip()
            or llm_scoring_cmd
            or os.getenv(LLM_SCORING_CMD_ENV, "").strip()
            or llm_deliberation_cmd
            or llm_consensus_cmd
        )
        _h_report_timeout = LLM_REPORT_SECTION_TIMEOUT_SECONDS

        h_asis_raw: dict = {}
        h_tobe_raw: dict = {}
        h_feasibility_raw: dict = {}
        h_exec_summary_raw: dict = {}

        if _h_report_cmd:
            # Parallel: As-Is + Feasibility (independent)
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_h_asis = executor.submit(
                    generate_asis_analysis_via_llm,
                    ranked=selected, states=states, scores=scores,
                    llm_command=_h_report_cmd, llm_timeout=_h_report_timeout,
                )
                future_h_feasibility = executor.submit(
                    generate_feasibility_evidence_via_llm,
                    ranked=selected, states=states, scores=scores,
                    llm_command=_h_report_cmd, llm_timeout=_h_report_timeout,
                    agent_definitions=agent_definitions, research_sources=research_sources,
                )

            h_asis_raw = future_h_asis.result()
            stage_log.append({"stage": "report_section_asis", "status": "completed" if h_asis_raw else "skipped",
                              "message": f"asis_full_text_len={len(h_asis_raw.get('full_text', ''))}"})

            h_feasibility_raw = future_h_feasibility.result()
            stage_log.append({"stage": "report_section_feasibility", "status": "completed" if h_feasibility_raw else "skipped",
                              "message": f"feasibility_full_text_len={len(h_feasibility_raw.get('full_text', ''))}"})

            # Sequential: To-Be depends on As-Is
            h_tobe_raw = generate_tobe_direction_via_llm(
                ranked=selected, states=states,
                llm_command=_h_report_cmd, llm_timeout=_h_report_timeout,
                asis_analysis=h_asis_raw, research_sources=research_sources,
            )
            stage_log.append({"stage": "report_section_tobe", "status": "completed" if h_tobe_raw else "skipped",
                              "message": f"tobe_full_text_len={len(h_tobe_raw.get('full_text', ''))}"})

            # Sequential: Executive Summary depends on all three
            h_exec_summary_raw = generate_executive_summary_via_llm(
                ranked=selected, states=states, scores=scores,
                llm_command=_h_report_cmd, llm_timeout=_h_report_timeout,
                research_sources=research_sources,
                asis_analysis=h_asis_raw, tobe_direction=h_tobe_raw,
                feasibility_evidence=h_feasibility_raw,
            )
            stage_log.append({"stage": "report_section_executive_summary", "status": "completed" if h_exec_summary_raw else "skipped",
                              "message": f"exec_summary_full_text_len={len(h_exec_summary_raw.get('full_text', ''))}"})

        markdown = as_markdown(
            workspace=workspace,
            top_topics=selected,
            states=states,
            scores=scores,
            ranked=ranked,
            agent_rankings=agent_rankings,
            phases=phases,
            synergy_lines=synergy,
            queries=queries,
            report_focus=report_focus,
            version_tag=version_tag,
            agent_definitions=agent_definitions,
            research_sources=research_sources,
            orchestration_profile=profile,
            orchestration_stages=stages,
            pipeline_stage_log=stage_log,
            service_scope=service_scope_list,
            feature_scope=feature_scope_list,
            hierarchical_analysis=hierarchical_analysis,
            executive_summary=h_exec_summary_raw,
            asis_analysis=h_asis_raw,
            tobe_direction=h_tobe_raw,
            feasibility_evidence=h_feasibility_raw,
        )

        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = output_dir / f"{output_name}_{ts}.md"
        js_path = output_dir / f"{output_name}_{ts}.json"

        data = to_json(
            states=states,
            scores=scores,
            scores_initial=scores,
            ranked=ranked,
            phases=phases,
            report_focus=report_focus,
            version_tag=version_tag,
            research_sources=research_sources,
            topic_keywords=topic_keywords,
            orchestration_profile=profile,
            orchestration_stages=stages,
            service_scope=service_scope_list,
            feature_scope=feature_scope_list,
            pipeline_stage_log=stage_log,
            hierarchical_analysis=hierarchical_analysis,
            executive_summary=h_exec_summary_raw,
            asis_analysis=h_asis_raw,
            tobe_direction=h_tobe_raw,
            feasibility_evidence=h_feasibility_raw,
            precomputed_agent_rankings=agent_rankings,
            precomputed_research_queries=queries,
        )
        md_path.write_text(markdown, encoding="utf-8")
        js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "markdown_path": str(md_path),
            "json_path": str(js_path),
            "agent_rankings": agent_rankings,
            "consensus": [],
            "consensus_summary": {},
            "top_topics": selected,
            "debate_rounds_executed": tier3_debate_rounds,
            "pipeline_decisions": [],
            "orchestration": {
                "profile": profile,
                "stages": stages,
                "service_scope": service_scope_list,
                "feature_scope": feature_scope_list,
                "stage_log": stage_log,
            },
            "hierarchical_analysis": hierarchical_analysis,
            "agent_mode": "hierarchical",
            "generated_at": data["generated_at"],
        }

    # ------------------------------------------------------------------
    # FLAT MODE (default)
    # ------------------------------------------------------------------

    # 4. Initialize scores — LLM scoring if configured, else neutral init
    resolved_scoring_cmd = llm_scoring_cmd
    if not resolved_scoring_cmd:
        resolved_scoring_cmd = os.getenv(LLM_SCORING_CMD_ENV, "").strip() or None

    from .llm_client import _get_provider
    if not resolved_scoring_cmd and _get_provider() is None:
        raise RuntimeError(
            "LLM scoring requires either --llm-scoring-cmd or "
            "GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT_ID."
        )
    if not personas:
        raise RuntimeError(
            "No personas loaded. Check persona directory at "
            f"{resolved_persona_dir}"
        )

    from .scoring import compute_agent_score

    all_agent_scores = score_all_agents(
        topic_states=states,
        personas=personas,
        agent_definitions=agent_definitions,
        llm_command=resolved_scoring_cmd,
        llm_timeout=llm_scoring_timeout,
        agent_filter=FLAT_MODE_AGENTS,
    )
    # Convert {agent_id: {topic_id: {feature: val}}} → {topic_id: {score_agent: val}}
    scores: dict[str, dict[str, float]] = {}
    for topic_id in states:
        per_topic: dict[str, float] = {}
        for agent_id, topic_scores in all_agent_scores.items():
            if topic_id in topic_scores:
                features = topic_scores[topic_id]
                persona = personas.get(agent_id)
                weights = persona.weights if persona else {}
                per_topic[_agent_score_key(agent_id)] = compute_agent_score(features, weights)
        scores[topic_id] = per_topic
    logger.info("LLM scoring completed for %d agents", len(all_agent_scores))

    discussion: list[dict] = []
    last_llm_state: dict[str, Any] | None = None

    # 5. LLM deliberation rounds
    effective_rounds = max(0, debate_rounds)
    llm_deliberation_command = llm_deliberation_cmd or os.getenv(LLM_DELIBERATION_CMD_ENV) or llm_consensus_cmd

    if ORCHESTRATION_STAGE_DELIBERATION in stages and effective_rounds > 0:
        if not llm_deliberation_command and _get_provider() is None:
            raise RuntimeError(
                "LLM deliberation requires either --llm-deliberation-cmd or "
                "GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT_ID."
            )
        stage_log.append({
            "stage": ORCHESTRATION_STAGE_DELIBERATION,
            "status": "started",
            "message": f"rounds={effective_rounds} profile={profile}",
        })
        for round_no in range(1, effective_rounds + 1):
            ranked_snapshot = build_final_score(states, scores)

            score_updates, decisions, round_summaries, llm_actions, llm_state = llm_deliberation_round(
                round_no=round_no,
                stages=stages,
                service_scope=service_scope_list,
                states=states,
                working_scores=scores,
                ranked=ranked_snapshot,
                previous_decisions=[d.to_dict() for d in pipeline_decisions],
                previous_discussion=discussion,
                command=llm_deliberation_command,
                timeout=max(1.0, llm_deliberation_timeout),
                agent_definitions=agent_definitions,
            )

            # Apply score adjustments
            for topic_id, per_agent in score_updates.items():
                if topic_id not in scores:
                    continue
                for agent_name, delta in per_agent.items():
                    agent_key = _agent_score_key(agent_name)
                    if agent_key not in scores[topic_id]:
                        continue
                    scores[topic_id][agent_key] = _clamp_score(
                        scores[topic_id][agent_key] + delta, 0.0, 10.0
                    )

            if decisions:
                pipeline_decisions.extend(decisions)
            if round_summaries:
                for summary in round_summaries:
                    if isinstance(summary, dict):
                        discussion.append(summary)
            if llm_actions:
                discussion.append({
                    "round": round_no,
                    "messages": llm_actions,
                    "stage": "llm_action_log",
                })

            status = llm_state.get("status", "unknown")
            if isinstance(llm_state, dict):
                last_llm_state = llm_state
            stage_log.append({
                "stage": ORCHESTRATION_STAGE_DELIBERATION,
                "status": status,
                "message": f"round={round_no}, decisions={len(decisions)}",
            })

            if status != "ok":
                if profile == ORCHESTRATION_PROFILE_STRICT:
                    raise RuntimeError(
                        f"LLM deliberation failed at round {round_no}: {llm_state}"
                    )
                stage_log.append({
                    "stage": ORCHESTRATION_STAGE_DELIBERATION,
                    "status": "stopped",
                    "message": f"non-strict early-stop on round={round_no}",
                })
                break
    else:
        discussion = []

    # 6. Finalize scores
    ranked = build_final_score(states, scores)
    selected = ranked[:top_k]

    # ------------------------------------------------------------------
    # 6.5 Interactive checkpoint: deliberation results review
    # ------------------------------------------------------------------
    if checkpoint is not None:
        ranked_items = [
            {
                "topic_id": item.get("topic_id"),
                "topic_name": item.get("topic_name"),
                "total_score": round(item.get("total_score", 0), 2),
                "rank": idx + 1,
            }
            for idx, item in enumerate(selected)
        ]
        cp_data = CheckpointData(
            stage="deliberation_complete",
            message=(
                f"Deliberation 완료. 상위 {len(selected)}개 토픽이 선정되었습니다. "
                f"이 결과로 리서치 + 리포트 생성을 진행할까요?"
            ),
            items=ranked_items,
            metadata={
                "debate_rounds": effective_rounds,
                "total_decisions": len(pipeline_decisions),
            },
        )
        cp_response = checkpoint(cp_data)
        if not cp_response.approved:
            return {
                "status": "cancelled",
                "stage": "deliberation_complete",
                "message": cp_response.feedback or "사용자가 deliberation 검토 단계에서 취소했습니다.",
                "ranked_topics": ranked_items,
            }

    _phase_llm_cmd = llm_deliberation_command or resolved_scoring_cmd or llm_consensus_cmd
    synergy = build_synergy_graph(states, selected)

    agent_rankings = build_agent_rankings(
        scores, top_k=top_k, agent_filter=FLAT_MODE_AGENTS,
    )

    if not pipeline_decisions:
        reason_parts: list[str] = []
        if isinstance(last_llm_state, dict):
            status_value = str(last_llm_state.get("status", "")).strip()
            reason_value = str(last_llm_state.get("reason", "")).strip()
            stderr_value = str(last_llm_state.get("stderr", "")).strip()
            if status_value:
                reason_parts.append(f"status={status_value}")
            if reason_value:
                reason_parts.append(f"reason={reason_value}")
            if stderr_value:
                reason_parts.append(f"stderr={stderr_value[:600]}")
        reason = " | ".join(reason_parts) or "unknown"
        pipeline_decisions = _build_fallback_decisions_via_llm(
            selected=selected,
            scores=scores,
            service_scope=service_scope_list,
            llm_command=llm_deliberation_command or resolved_scoring_cmd or llm_consensus_cmd,
        )
        stage_log.append({
            "stage": ORCHESTRATION_STAGE_DELIBERATION,
            "status": "fallback_decisions",
            "message": (
                f"LLM deliberation had no decisions; fallback generated "
                f"{len(pipeline_decisions)} decisions ({reason})"
            ),
        })
        if not pipeline_decisions:
            raise RuntimeError(
                "LLM deliberation produced no decisions and fallback could not build decisions."
            )

    selected_decisions = _pipeline_decisions_to_topic_records(
        pipeline_decisions, agent_definitions=agent_definitions,
    )

    # 7. Consensus
    if not llm_consensus_cmd and not llm_deliberation_command and _get_provider() is None:
        raise RuntimeError(
            "LLM consensus requires either --llm-consensus-cmd, "
            "--llm-deliberation-cmd, or "
            "GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT_ID."
        )

    # Build deliberation risk summary for consensus
    _delib_risk_summary: list[dict] = []
    for d in pipeline_decisions:
        _delib_risk_summary.append({
            "topic_id": d.topic_id,
            "topic_name": d.topic_name,
            "risk": d.risk,
            "confidence": d.confidence,
            "score_delta": d.score_delta,
            "fail_label": d.fail_label,
            "rationale": d.rationale[:200],
        })

    consensus_summary = apply_hybrid_consensus(
        ranked=ranked,
        states=states,
        scores=scores,
        agent_rankings=agent_rankings,
        discussion=discussion,
        top_k=top_k,
        command=llm_consensus_cmd,
        timeout=llm_consensus_timeout,
        agent_definitions=agent_definitions,
        deliberation_risk_summary=_delib_risk_summary,
    )

    if consensus_summary.get("status") != "ok":
        fallback_ids = [item["topic_id"] for item in ranked[:top_k]]
        fail_reason = str(consensus_summary.get("reason", consensus_summary.get("status", "failed"))).strip()
        consensus_summary = {
            "method": "llm-fallback-ranked",
            "status": "ok",
            "final_consensus_ids": fallback_ids,
            "final_rationale": (
                "LLM consensus failed; fallback consensus selected by final weighted ranking."
            ),
            "llm": consensus_summary.get("llm", {}),
            "llm_raw_output": consensus_summary.get("llm_raw_output", ""),
            "concerns": consensus_summary.get("concerns", []),
            "vetoed": [],
            "gating": [],
            "payload": consensus_summary.get("payload", {}),
            "target_size": min(top_k, len(ranked)),
            "requested_top_k": top_k,
            "fallback_reason": fail_reason,
        }
        stage_log.append({
            "stage": ORCHESTRATION_STAGE_DELIBERATION,
            "status": "fallback_consensus",
            "message": f"LLM consensus failed; fallback applied ({fail_reason})",
        })

    stage_log.append({
        "stage": ORCHESTRATION_STAGE_DELIBERATION,
        "status": "consensus_completed",
        "message": f"consensus_method={consensus_summary.get('method', 'llm-only')}",
    })

    if ORCHESTRATION_STAGE_EXECUTION in stages:
        stage_log.append({
            "stage": ORCHESTRATION_STAGE_EXECUTION,
            "status": "planned",
            "message": f"decision_objects={len(pipeline_decisions)}",
        })

    # 8. Research queries + sources
    queries = build_research_queries(selected, topic_keywords=topic_keywords, top_k=min(6, top_k))
    output_dir.mkdir(parents=True, exist_ok=True)
    research_sources, search_warnings = build_sources_file(
        output_dir=output_dir,
        version_tag=version_tag,
        report_focus=report_focus,
        top_topics=selected,
        topic_keywords=topic_keywords,
    )
    if search_warnings:
        stage_log.append({
            "stage": "research_search",
            "status": "partial",
            "message": f"search_warnings={len(search_warnings)} (some APIs failed)",
            "warnings": [
                {"provider": w.get("provider", ""), "topic": w.get("topic", ""), "error": w.get("search_error", "")}
                for w in search_warnings[:10]
            ],
        })

    # 8.5 Parallel Group A+C: strategy cards + QA verification + phase plan
    llm_strategy_cmd = resolved_scoring_cmd or llm_deliberation_command or llm_consensus_cmd
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_strategy = executor.submit(
            generate_strategy_cards_via_llm,
            top_topics=selected,
            states=states,
            llm_command=llm_strategy_cmd,
            llm_timeout=30.0,
            agent_decisions=selected_decisions,
            sources=research_sources,
        )
        future_qa = executor.submit(
            run_qa_verification_via_llm,
            top_topics=selected,
            states=states,
            scores=scores,
            llm_command=llm_strategy_cmd,
            llm_timeout=30.0,
        )
        future_phases = executor.submit(
            build_phase_plan_via_llm,
            selected,
            top_k=top_k,
            llm_command=_phase_llm_cmd,
        )

    strategy_cards = future_strategy.result()
    stage_log.append({
        "stage": "strategy_cards",
        "status": "completed",
        "message": f"llm_strategy_cards={len(strategy_cards)}",
    })

    qa_verification = future_qa.result()
    stage_log.append({
        "stage": "qa_verification",
        "status": "completed",
        "message": f"qa_results={len(qa_verification)}",
    })

    phases = future_phases.result()
    stage_log.append({
        "stage": "phase_plan",
        "status": "completed",
        "message": f"phases={len(phases)}",
    })

    # 8.6 LLM report sections (As-Is → To-Be → Feasibility → Executive Summary)
    llm_report_cmd = (
        os.getenv(LLM_REPORT_SECTION_CMD_ENV, "").strip()
        or resolved_scoring_cmd
        or llm_deliberation_command
        or llm_consensus_cmd
    )
    _report_timeout = LLM_REPORT_SECTION_TIMEOUT_SECONDS

    asis_analysis_raw: dict = {}
    tobe_direction_raw: dict = {}
    feasibility_evidence_raw: dict = {}
    executive_summary_raw: dict = {}

    if llm_report_cmd:
        # Parallel Group B: As-Is + Feasibility (independent of each other)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_asis = executor.submit(
                generate_asis_analysis_via_llm,
                ranked=selected,
                states=states,
                scores=scores,
                llm_command=llm_report_cmd,
                llm_timeout=_report_timeout,
            )
            future_feasibility = executor.submit(
                generate_feasibility_evidence_via_llm,
                ranked=selected,
                states=states,
                scores=scores,
                llm_command=llm_report_cmd,
                llm_timeout=_report_timeout,
                agent_definitions=agent_definitions,
                consensus_summary=consensus_summary,
                strategy_cards=strategy_cards,
                research_sources=research_sources,
                pipeline_decisions=pipeline_decisions,
            )

        asis_analysis_raw = future_asis.result()
        stage_log.append({
            "stage": "report_section_asis",
            "status": "completed" if asis_analysis_raw else "skipped",
            "message": f"asis_full_text_len={len(asis_analysis_raw.get('full_text', ''))}",
        })

        feasibility_evidence_raw = future_feasibility.result()
        stage_log.append({
            "stage": "report_section_feasibility",
            "status": "completed" if feasibility_evidence_raw else "skipped",
            "message": f"feasibility_full_text_len={len(feasibility_evidence_raw.get('full_text', ''))}",
        })

        # Sequential: To-Be depends on As-Is
        tobe_direction_raw = generate_tobe_direction_via_llm(
            ranked=selected,
            states=states,
            llm_command=llm_report_cmd,
            llm_timeout=_report_timeout,
            asis_analysis=asis_analysis_raw,
            strategy_cards=strategy_cards,
            research_sources=research_sources,
        )
        stage_log.append({
            "stage": "report_section_tobe",
            "status": "completed" if tobe_direction_raw else "skipped",
            "message": f"tobe_full_text_len={len(tobe_direction_raw.get('full_text', ''))}",
        })

        # Sequential: Executive Summary depends on As-Is + To-Be + Feasibility
        executive_summary_raw = generate_executive_summary_via_llm(
            ranked=selected,
            states=states,
            scores=scores,
            llm_command=llm_report_cmd,
            llm_timeout=_report_timeout,
            consensus_summary=consensus_summary,
            strategy_cards=strategy_cards,
            research_sources=research_sources,
            agent_decisions=selected_decisions,
            asis_analysis=asis_analysis_raw,
            tobe_direction=tobe_direction_raw,
            feasibility_evidence=feasibility_evidence_raw,
        )
        stage_log.append({
            "stage": "report_section_executive_summary",
            "status": "completed" if executive_summary_raw else "skipped",
            "message": f"exec_summary_full_text_len={len(executive_summary_raw.get('full_text', ''))}",
        })

    # 9. Generate reports
    markdown = as_markdown(
        workspace=workspace,
        top_topics=selected,
        states=states,
        scores=scores,
        ranked=ranked,
        agent_rankings=agent_rankings,
        phases=phases,
        synergy_lines=synergy,
        queries=queries,
        report_focus=report_focus,
        version_tag=version_tag,
        agent_definitions=agent_definitions,
        research_sources=research_sources,
        agent_decisions=selected_decisions,
        discussion=discussion,
        debate_rounds=debate_rounds,
        consensus_summary=consensus_summary,
        orchestration_profile=profile,
        orchestration_stages=stages,
        pipeline_decisions=pipeline_decisions,
        pipeline_stage_log=stage_log,
        service_scope=service_scope_list,
        feature_scope=feature_scope_list,
        strategy_cards_prebuilt=strategy_cards,
        qa_verification=qa_verification,
        executive_summary=executive_summary_raw,
        asis_analysis=asis_analysis_raw,
        tobe_direction=tobe_direction_raw,
        feasibility_evidence=feasibility_evidence_raw,
    )

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"{output_name}_{ts}.md"
    js_path = output_dir / f"{output_name}_{ts}.json"

    data = to_json(
        states=states,
        scores=scores,
        scores_initial=scores,
        ranked=ranked,
        phases=phases,
        report_focus=report_focus,
        version_tag=version_tag,
        research_sources=research_sources,
        topic_keywords=topic_keywords,
        selected_agent_decisions=selected_decisions,
        discussion=discussion,
        debate_rounds=debate_rounds,
        consensus_summary=consensus_summary,
        orchestration_profile=profile,
        orchestration_stages=stages,
        service_scope=service_scope_list,
        feature_scope=feature_scope_list,
        pipeline_decisions=pipeline_decisions,
        pipeline_stage_log=stage_log,
        strategy_cards_prebuilt=strategy_cards,
        qa_verification=qa_verification,
        executive_summary=executive_summary_raw,
        asis_analysis=asis_analysis_raw,
        tobe_direction=tobe_direction_raw,
        feasibility_evidence=feasibility_evidence_raw,
        precomputed_agent_rankings=agent_rankings,
        precomputed_research_queries=queries,
    )
    md_path.write_text(markdown, encoding="utf-8")
    js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown_path": str(md_path),
        "json_path": str(js_path),
        "agent_rankings": agent_rankings,
        "consensus": consensus_summary.get("final_consensus_ids", []),
        "consensus_summary": consensus_summary,
        "top_topics": selected,
        "debate_rounds_executed": len(discussion),
        "pipeline_decisions": [item.to_dict() for item in pipeline_decisions],
        "orchestration": {
            "profile": profile,
            "stages": stages,
            "service_scope": service_scope_list,
            "feature_scope": feature_scope_list,
            "stage_log": stage_log,
        },
        "agent_mode": "flat",
        "generated_at": data["generated_at"],
    }
