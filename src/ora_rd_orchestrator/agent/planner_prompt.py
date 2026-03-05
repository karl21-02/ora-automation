"""Planner system prompt builder for the ReAct agent.

Generates the system instruction that guides the LLM to act as an R&D
analysis planner — reasoning about the current state and choosing the
right tools to call next.
"""
from __future__ import annotations

from .state import AgentState
from .tool_registry import ToolRegistry


def build_planner_system_prompt(state: AgentState, registry: ToolRegistry) -> str:
    """Build the full system prompt for the planner LLM.

    Includes:
      1. Agent role description
      2. General R&D workflow guidance
      3. Current state summary
      4. Available tools with descriptions
    """
    tool_descriptions = _format_tool_descriptions(registry)
    state_summary = state.summary_for_llm()

    return f"""\
당신은 Ora R&D Orchestrator의 자율 에이전트입니다.
사용자의 요청을 분석하고, 필요한 도구를 순서대로 호출하여 R&D 분석을 수행합니다.

## 역할
- 사용자 요청을 이해하고 필요한 분석 단계를 판단합니다.
- 각 도구를 호출한 후 결과를 확인하고 다음 단계를 결정합니다.
- 모든 필요한 단계가 완료되면 최종 결과를 텍스트로 요약합니다.

## 일반적인 R&D 분석 워크플로우
전체 분석이 필요한 경우 일반적으로 다음 순서를 따릅니다:
1. load_personas → 에이전트 페르소나 로드
2. collect_workspace_summary → 워크스페이스 파일 요약
3. discover_topics → R&D 토픽 발견
4. analyze_workspace → 토픽별 증거 수집
5. score_all_topics → 에이전트별 토픽 점수 매기기
6. run_deliberation → 다중 라운드 토론
7. apply_consensus → 최종 합의
8. search_research_sources → 학술 논문 검색
9. generate_full_report → 보고서 생성

하지만 사용자 요청에 따라 일부 단계만 실행할 수 있습니다.
예를 들어 "리서치만 해줘"라면 search_research_sources만 호출하면 됩니다.

## 현재 상태
{state_summary}

## 사용 가능한 도구
{tool_descriptions}

## 행동 규칙
- 이미 완료된 단계는 다시 실행하지 마세요 (위 "현재 상태" 참조).
- 도구 호출이 실패하면 에러를 확인하고 대안을 시도하세요.
- 모든 작업이 완료되면 도구를 호출하지 말고 텍스트로 최종 요약을 제공하세요.
- 한 번에 하나의 도구만 호출하세요.
- 응답은 한국어로 작성하세요.
"""


def _format_tool_descriptions(registry: ToolRegistry) -> str:
    """Format tool list as human-readable text for the system prompt."""
    lines: list[str] = []
    for tool in registry.list_tools():
        params = ""
        if tool.parameters:
            param_strs = []
            for p in tool.parameters:
                req = " (필수)" if p.required else ""
                param_strs.append(f"    - {p.name}: {p.description}{req}")
            params = "\n" + "\n".join(param_strs)
        lines.append(f"- **{tool.name}**: {tool.description}{params}")
    return "\n".join(lines)
