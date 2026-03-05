from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import generate_report
from .types import CheckpointCallback, CheckpointData, CheckpointResponse


def _parse_list(values: str | None) -> list[str]:
    if not values:
        return []
    return [item.strip() for item in values.split(",") if item.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ora-rd-orchestrator",
        description="Run multi-agent R&D strategy analysis over Ora projects.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root to scan (default: .)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=6,
        help="Number of final topics to output.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to store output md/json reports.",
    )
    parser.add_argument(
        "--output-name",
        default="rd_research_report",
        help="Base file name without extension.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=1500,
        help="Hard stop for scanned files to control runtime.",
    )
    parser.add_argument(
        "--extensions",
        default="md,txt,py,java,kt,ts,tsx,json,yml,yaml,properties,xml,ini,cfg,sh,gradle,toml",
        help="Comma-separated file extensions to include.",
    )
    parser.add_argument(
        "--ignore-dirs",
        default=".git,.idea,.venv,venv,node_modules,target,build,dist,.gradle,.mvn,__pycache__,.pytest_cache",
        help="Comma-separated directories to skip.",
    )
    parser.add_argument(
        "--focus",
        default="",
        help="Optional focus label for report title (예: OraB2bAndroid).",
    )
    parser.add_argument(
        "--version-tag",
        default="V10",
        help="Report version tag shown in markdown header.",
    )
    parser.add_argument(
        "--single-strategy",
        action="store_true",
        help="Force TOP-1 output (one R&D strategy per report).",
    )
    parser.add_argument(
        "--debate-rounds",
        type=int,
        default=2,
        help="Number of agent deliberation rounds before final ranking (default: 2).",
    )
    parser.add_argument(
        "--orchestration-profile",
        default="standard",
        help="Orchestration profile (standard|strict).",
    )
    parser.add_argument(
        "--orchestration-stages",
        default="analysis,deliberation,execution",
        help="Comma-separated stages (analysis,deliberation,execution).",
    )
    parser.add_argument(
        "--service-scope",
        default="",
        help="Comma-separated service scope (b2b,b2b-android,b2c,ai,telecom,docs).",
    )
    parser.add_argument(
        "--feature-scope",
        default="",
        help="Comma-separated feature scope labels.",
    )
    parser.add_argument(
        "--llm-deliberation-cmd",
        default=None,
        help="External command for LLM deliberation rounds (JSON in/out).",
    )
    parser.add_argument(
        "--llm-deliberation-timeout",
        type=float,
        default=8.0,
        help="LLM deliberation command timeout seconds.",
    )
    parser.add_argument(
        "--llm-consensus-cmd",
        default=None,
        help="External command to run LLM-assisted consensus (JSON in, JSON out).",
    )
    parser.add_argument(
        "--llm-consensus-timeout",
        type=float,
        default=8.0,
        help="LLM consensus command timeout seconds (default: 8.0).",
    )
    parser.add_argument(
        "--history",
        nargs="*",
        default=[],
        help="Optional markdown files containing past research reports (V7, V8, V9...).",
    )
    parser.add_argument(
        "--agent-mode",
        default="flat",
        choices=["flat", "hierarchical", "react"],
        help="Agent mode: flat (default, 7-agent), hierarchical (4-tier, 14-agent), or react (autonomous ReAct agent).",
    )
    parser.add_argument(
        "--tier3-debate-rounds",
        type=int,
        default=2,
        help="Number of Tier 3 cross-domain debate rounds in hierarchical mode (default: 2).",
    )
    parser.add_argument(
        "--qa-gate-threshold",
        type=float,
        default=3.5,
        help="QA gate threshold for hierarchical mode (default: 3.5).",
    )
    parser.add_argument(
        "--subordinate-blend",
        type=float,
        default=0.60,
        help="Tier 2 subordinate blend ratio (default: 0.60).",
    )
    parser.add_argument(
        "--persona-dir",
        default=None,
        help="Directory containing persona YAML files (default: built-in personas/).",
    )
    parser.add_argument(
        "--llm-topic-discovery-cmd",
        default=None,
        help="External command for LLM-driven topic discovery (JSON in/out).",
    )
    parser.add_argument(
        "--llm-scoring-cmd",
        default=None,
        help="External command for LLM-driven agent scoring (JSON in/out).",
    )
    parser.add_argument(
        "--llm-scoring-timeout",
        type=float,
        default=10.0,
        help="LLM scoring command timeout seconds (default: 10.0).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive checkpoints — pause after topic discovery and deliberation for user approval.",
    )
    return parser


def _cli_checkpoint(data: CheckpointData) -> CheckpointResponse:
    """Interactive checkpoint for CLI: prints summary and asks for approval."""
    print(f"\n{'='*60}")
    print(f"[checkpoint] {data.stage}")
    print(f"{'='*60}")
    print(data.message)
    if data.items:
        for item in data.items:
            label = item.get("topic_name") or item.get("topic_id", "?")
            extra = ""
            if "confidence" in item:
                extra += f" (confidence={item['confidence']:.2f})"
            if "total_score" in item:
                extra += f" (score={item['total_score']})"
            if "rank" in item:
                extra = f" #{item['rank']}" + extra
            print(f"  - {label}{extra}")
    print()
    try:
        answer = input("[checkpoint] 진행할까요? (y/n, default=y): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return CheckpointResponse(approved=False, feedback="EOF/Interrupt")
    if answer in ("n", "no"):
        return CheckpointResponse(approved=False, feedback="사용자가 CLI에서 거부")
    return CheckpointResponse(approved=True)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()

    # --- ReAct agent mode ---
    if (args.agent_mode or "flat").strip().lower() == "react":
        from .agent import run_agent_loop

        result = run_agent_loop(
            user_message=args.focus or "R&D 분석을 수행해주세요",
            workspace_path=str(workspace),
            top_k=max(1, args.top),
            report_focus=args.focus.strip() if args.focus else "",
            service_scope=_parse_list(args.service_scope),
            output_dir=str(output_dir),
            output_name=args.output_name,
            persona_dir=args.persona_dir.strip() if args.persona_dir else None,
        )
        print(f"[agent] {result['response'][:500]}")
        print(f"[agent] stop_reason={result['stop_reason']}, iterations={result['iterations']}")
        return 0

    result = generate_report(
        workspace=workspace,
        top_k=1 if args.single_strategy else max(1, args.top),
        output_dir=output_dir,
        output_name=args.output_name,
        max_files=max(1, args.max_files),
        extensions=_parse_list(args.extensions),
        ignore_dirs=set(_parse_list(args.ignore_dirs)),
        history_files=[Path(p).expanduser().resolve() for p in args.history],
        report_focus=(args.focus.strip() if args.focus else ""),
        version_tag=args.version_tag.strip() if args.version_tag else "V10",
        debate_rounds=max(0, args.debate_rounds),
        orchestration_profile=args.orchestration_profile.strip().lower() if args.orchestration_profile else "standard",
        orchestration_stages=_parse_list(args.orchestration_stages),
        service_scope=_parse_list(args.service_scope),
        feature_scope=_parse_list(args.feature_scope),
        llm_deliberation_cmd=args.llm_deliberation_cmd.strip() if args.llm_deliberation_cmd else None,
        llm_deliberation_timeout=max(1.0, args.llm_deliberation_timeout),
        llm_consensus_cmd=args.llm_consensus_cmd.strip() if args.llm_consensus_cmd else None,
        llm_consensus_timeout=max(1.0, args.llm_consensus_timeout),
        agent_mode=args.agent_mode.strip().lower() if args.agent_mode else "flat",
        tier3_debate_rounds=max(0, args.tier3_debate_rounds),
        qa_gate_threshold=max(0.0, args.qa_gate_threshold),
        subordinate_blend=max(0.0, min(1.0, args.subordinate_blend)),
        persona_dir=args.persona_dir.strip() if args.persona_dir else None,
        llm_topic_discovery_cmd=args.llm_topic_discovery_cmd.strip() if args.llm_topic_discovery_cmd else None,
        llm_scoring_cmd=args.llm_scoring_cmd.strip() if args.llm_scoring_cmd else None,
        llm_scoring_timeout=max(1.0, args.llm_scoring_timeout),
        checkpoint=_cli_checkpoint if args.interactive else None,
    )

    if result.get("status") == "cancelled":
        print(f"[cancelled] stage={result.get('stage', '?')}: {result.get('message', '')}")
        return 0

    print(f"[done] markdown: {result['markdown_path']}")
    print(f"[done] json: {result['json_path']}")
    print(f"[summary] agent-mode: {result.get('agent_mode', 'flat')}")
    print(
        "[summary] final-topics: "
        + ", ".join(item["topic_name"] for item in result["top_topics"])
    )
    print(
        f"[summary] debate-rounds: requested {max(0, args.debate_rounds)} / "
        f"executed {result.get('debate_rounds_executed', 0)}"
    )
    orchestration = result.get("orchestration", {})
    print(
        "[summary] orchestration: "
        + f"profile={orchestration.get('profile', args.orchestration_profile)} "
        + f"stages={','.join(orchestration.get('stages', _parse_list(args.orchestration_stages)))}"
    )
    if result.get("agent_mode") == "hierarchical":
        h_analysis = result.get("hierarchical_analysis", {})
        t2_flags = h_analysis.get("tier2", {}).get("flags", {})
        flagged = sum(1 for v in t2_flags.values() if v)
        print(f"[summary] hierarchical: tier3-rounds={args.tier3_debate_rounds} qa-flagged={flagged}")
    else:
        print(
            "[summary] consensus-method: "
            + str(result.get("consensus_summary", {}).get("method", "llm-only"))
        )

        topic_by_id = {
            item["topic_id"]: item["topic_name"]
            for item in result["top_topics"]
        }
        consensus_topic_names = [
            topic_by_id.get(topic_id, topic_id) for topic_id in result.get("consensus", [])
        ]
        print(
            "[summary] consensus: "
            + ", ".join(consensus_topic_names[:3])
        )
    print(
        "[summary] agent-rankings: "
        + ", ".join(
            f"{agent}={rankings[0] if rankings else 'N/A'}"
            for agent, rankings in result["agent_rankings"].items()
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
