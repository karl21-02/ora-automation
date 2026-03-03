from __future__ import annotations

import argparse
from pathlib import Path

from .engine import generate_report


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()

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
        llm_consensus_cmd=args.llm_consensus_cmd.strip() if args.llm_consensus_cmd else None,
        llm_consensus_timeout=max(1.0, args.llm_consensus_timeout),
    )

    print(f"[done] markdown: {result['markdown_path']}")
    print(f"[done] json: {result['json_path']}")
    print(
        "[summary] final-topics: "
        + ", ".join(item["topic_name"] for item in result["top_topics"])
    )
    print(
        f"[summary] debate-rounds: requested {max(0, args.debate_rounds)} / "
        f"executed {result.get('debate_rounds_executed', 0)}"
    )
    print(
        "[summary] consensus-method: "
        + str(result.get("consensus_summary", {}).get("method", "rule-only"))
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
