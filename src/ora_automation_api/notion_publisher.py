"""Transform R&D report JSON into Notion API payloads and publish."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .notion_client import NotionClient

logger = logging.getLogger(__name__)

# Notion rich-text limit per element
MAX_TEXT_LEN = 2000
# Notion children per single append call
MAX_BLOCKS_PER_APPEND = 100


class NotionPublisher:
    """Converts R&D JSON reports into Notion pages/DB rows."""

    def __init__(
        self,
        client: NotionClient,
        reports_db_id: str,
        topics_db_id: str,
        hub_page_id: str,
    ) -> None:
        self.client = client
        self.reports_db_id = reports_db_id
        self.topics_db_id = topics_db_id
        self.hub_page_id = hub_page_id

    # ── Public API ────────────────────────────────────────────────────

    def publish_report(self, report_data: dict, report_path: str) -> dict:
        """Orchestrate full publish: report row + detail page + topic entries."""
        report_row = self._create_report_row(report_data, report_path)
        report_page_id = report_row["id"]
        report_url = report_row.get("url", "")

        detail_page = self._create_report_detail_page(report_page_id, report_data)
        topic_pages = self._create_topic_entries(report_data, report_page_id)

        return {
            "report_page_id": report_page_id,
            "report_url": report_url,
            "detail_page_id": detail_page["id"],
            "topic_pages": topic_pages,
        }

    # ── Report DB row ─────────────────────────────────────────────────

    def _create_report_row(self, data: dict, path: str) -> dict:
        focus = data.get("report_focus", "")
        version = data.get("report_version", "")
        ranked = data.get("ranked", [])
        section_status = data.get("section_status", {})
        consensus = data.get("consensus_summary") or {}
        orchestration = data.get("orchestration", {})

        top_score = ranked[0].get("total_score", 0) if ranked else 0

        properties: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": f"R&D Report — {focus or version}"[:100]}}]},
            "Report Date": {"date": {"start": data.get("generated_at", datetime.utcnow().isoformat())[:10]}},
            "Focus": {"rich_text": [{"text": {"content": (focus or "general")[:200]}}]},
            "Version": {"rich_text": [{"text": {"content": version[:100]}}]},
            "Topic Count": {"number": len(ranked)},
            "Top Score": {"number": round(top_score, 2)},
            "Debate Rounds": {"number": data.get("debate_rounds_executed", 0)},
            "Profile": {"rich_text": [{"text": {"content": orchestration.get("profile", "standard")[:50]}}]},
        }

        # Section status as rich_text summary
        status_parts = [f"{k}:{v}" for k, v in section_status.items()]
        if status_parts:
            properties["Section Status"] = {
                "rich_text": [{"text": {"content": " | ".join(status_parts)[:200]}}],
            }

        return self.client.create_page(
            parent={"database_id": self.reports_db_id},
            properties=properties,
            icon={"emoji": "\U0001f4ca"},
        )

    # ── Detail page (blocks) ─────────────────────────────────────────

    def _create_report_detail_page(self, parent_page_id: str, data: dict) -> dict:
        blocks = self._build_report_blocks(data)

        # Create child page under report row
        first_batch = blocks[0] if blocks else []
        page = self.client.create_page(
            parent={"page_id": parent_page_id},
            properties={"title": [{"text": {"content": "Report Details"}}]},
            children=first_batch,
        )

        # Append remaining batches
        for batch in blocks[1:]:
            self.client.append_blocks(page["id"], batch)

        return page

    # ── Topic entries ─────────────────────────────────────────────────

    def _create_topic_entries(self, data: dict, report_page_id: str) -> list[dict]:
        ranked = data.get("ranked", [])
        results = []
        for idx, item in enumerate(ranked):
            features = item.get("features", {})
            properties: dict[str, Any] = {
                "Name": {"title": [{"text": {"content": item.get("topic_name", "")[:100]}}]},
                "Topic ID": {"rich_text": [{"text": {"content": item.get("topic_id", "")[:100]}}]},
                "Total Score": {"number": round(item.get("total_score", 0), 2)},
                "Impact": {"number": round(features.get("impact", 0), 2)},
                "Feasibility": {"number": round(features.get("feasibility", 0), 2)},
                "Novelty": {"number": round(features.get("novelty", 0), 2)},
                "Risk Penalty": {"number": round(features.get("risk_penalty", 0), 2)},
                "Research Signal": {"number": round(features.get("research_signal", 0), 2)},
                "Project Count": {"number": item.get("project_count", 0)},
                "Rank": {"number": idx + 1},
            }

            try:
                result = self.client.create_page(
                    parent={"database_id": self.topics_db_id},
                    properties=properties,
                    icon={"emoji": "\U0001f9ea"},
                )
                results.append({
                    "topic_id": item.get("topic_id", ""),
                    "notion_page_id": result["id"],
                })
            except Exception as exc:
                logger.warning("Failed to create topic entry %s: %s", item.get("topic_id"), exc)

        return results

    # ── Block builder ─────────────────────────────────────────────────

    def _build_report_blocks(self, data: dict) -> list[list[dict]]:
        """Build Notion blocks from report data, split into batches of 100."""
        blocks: list[dict] = []

        # Executive Summary
        exec_summary = data.get("executive_summary") or {}
        full_text = exec_summary.get("full_text", "")
        if full_text:
            blocks.append(_heading2("Executive Summary"))
            blocks.extend(_paragraphs(full_text))

        # Top Topics table summary
        ranked = data.get("ranked", [])
        if ranked:
            blocks.append(_heading2("Top R&D Topics"))
            for idx, item in enumerate(ranked[:10], start=1):
                features = item.get("features", {})
                line = (
                    f"{idx}. {item.get('topic_name', '')} — "
                    f"Score: {item.get('total_score', 0):.1f} "
                    f"(Impact {features.get('impact', 0):.1f} / "
                    f"Feasibility {features.get('feasibility', 0):.1f} / "
                    f"Novelty {features.get('novelty', 0):.1f})"
                )
                blocks.extend(_paragraphs(line))

        # As-Is Analysis
        asis = data.get("asis_analysis") or {}
        asis_text = asis.get("full_text", "")
        if asis_text:
            blocks.append(_heading2("As-Is Analysis"))
            blocks.extend(_paragraphs(asis_text))

        # To-Be Direction
        tobe = data.get("tobe_direction") or {}
        tobe_text = tobe.get("full_text", "")
        if tobe_text:
            blocks.append(_heading2("To-Be Direction"))
            blocks.extend(_paragraphs(tobe_text))

        # Strategy Cards
        cards = data.get("strategy_cards", [])
        if cards:
            blocks.append(_heading2("Strategy Cards"))
            for card in cards:
                blocks.append(_heading3(f"#{card.get('rank', '?')} {card.get('topic_name', '')}"))
                edge = card.get("competitive_edge", "")
                if edge:
                    blocks.append(_callout(edge, emoji="\U0001f3af"))
                ideas = card.get("innovation_ideas", [])
                for idea in ideas:
                    if isinstance(idea, dict):
                        blocks.extend(_paragraphs(f"- {idea.get('idea', '')}"))

        # Feasibility Evidence
        feas = data.get("feasibility_evidence") or {}
        feas_text = feas.get("full_text", "")
        if feas_text:
            blocks.append(_heading2("Feasibility Evidence"))
            blocks.extend(_paragraphs(feas_text))

        # Research Sources
        sources = data.get("research_sources", [])
        if sources:
            blocks.append(_heading2("Research Sources"))
            for src in sources[:20]:
                url = src.get("url", "")
                title = src.get("title", url)
                if url:
                    blocks.append(_bookmark(url, title))

        # Consensus
        consensus = data.get("consensus_summary") or {}
        rationale = consensus.get("final_rationale", "")
        if rationale:
            blocks.append(_heading2("Consensus"))
            blocks.append(_quote(rationale))

        return _split_into_batches(blocks)

    # ── Text splitting ────────────────────────────────────────────────

    @staticmethod
    def _split_text(text: str, max_len: int = MAX_TEXT_LEN) -> list[dict]:
        return _split_rich_text(text, max_len)


# ── Module-level block helpers ────────────────────────────────────────


def _rich_text(text: str) -> list[dict]:
    return _split_rich_text(text)


def _split_rich_text(text: str, max_len: int = MAX_TEXT_LEN) -> list[dict]:
    if not text:
        return [{"type": "text", "text": {"content": ""}}]
    parts = []
    remaining = text
    while remaining:
        chunk = remaining[:max_len]
        parts.append({"type": "text", "text": {"content": chunk}})
        remaining = remaining[max_len:]
    return parts


def _heading2(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich_text(text[:MAX_TEXT_LEN])},
    }


def _heading3(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": _rich_text(text[:MAX_TEXT_LEN])},
    }


def _paragraphs(text: str) -> list[dict]:
    """Split long text into multiple paragraph blocks."""
    if not text:
        return []
    blocks = []
    remaining = text
    while remaining:
        chunk = remaining[:MAX_TEXT_LEN]
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
        })
        remaining = remaining[MAX_TEXT_LEN:]
    return blocks


def _callout(text: str, emoji: str = "\U0001f4a1") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(text[:MAX_TEXT_LEN]),
            "icon": {"emoji": emoji},
        },
    }


def _quote(text: str) -> dict:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": _rich_text(text[:MAX_TEXT_LEN])},
    }


def _bookmark(url: str, caption: str = "") -> dict:
    block: dict[str, Any] = {
        "object": "block",
        "type": "bookmark",
        "bookmark": {"url": url},
    }
    if caption:
        block["bookmark"]["caption"] = _rich_text(caption[:MAX_TEXT_LEN])
    return block


def _split_into_batches(blocks: list[dict], batch_size: int = MAX_BLOCKS_PER_APPEND) -> list[list[dict]]:
    if not blocks:
        return []
    return [blocks[i:i + batch_size] for i in range(0, len(blocks), batch_size)]


# ── Auto-publish helper (called from service.py) ─────────────────────


def auto_publish_latest_report(run_id: str, db: Any) -> None:
    """Auto-publish the latest report for a completed run to Notion.

    Called from service.execute_run() when auto_publish_notion is enabled.
    """
    import json
    from pathlib import Path

    from .config import settings
    from .models import NotionSyncState

    if not settings.notion_api_token:
        logger.debug("Notion auto-publish skipped: no API token")
        return

    # Find the report file from the run output directory
    run_dir = settings.run_output_dir / run_id
    if not run_dir.exists():
        logger.debug("Notion auto-publish skipped: run dir not found %s", run_dir)
        return

    # Look for JSON report files
    json_files = sorted(run_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    report_file = None
    report_data = None
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if "ranked" in data and "report_version" in data:
                report_file = jf
                report_data = data
                break
        except Exception:
            continue

    if not report_file or not report_data:
        logger.debug("Notion auto-publish skipped: no valid report JSON in %s", run_dir)
        return

    # Check if setup was done
    from sqlalchemy import select
    hub_row = db.scalar(
        select(NotionSyncState).where(
            NotionSyncState.entity_type == "hub_page",
            NotionSyncState.entity_key == "singleton",
        )
    )
    if not hub_row:
        logger.warning("Notion auto-publish skipped: setup not done")
        return

    reports_db_row = db.scalar(
        select(NotionSyncState).where(
            NotionSyncState.entity_type == "reports_db",
            NotionSyncState.entity_key == "singleton",
        )
    )
    topics_db_row = db.scalar(
        select(NotionSyncState).where(
            NotionSyncState.entity_type == "topics_db",
            NotionSyncState.entity_key == "singleton",
        )
    )

    if not reports_db_row or not topics_db_row:
        logger.warning("Notion auto-publish skipped: DB IDs not found")
        return

    client = NotionClient()
    publisher = NotionPublisher(
        client=client,
        reports_db_id=reports_db_row.notion_page_id,
        topics_db_id=topics_db_row.notion_page_id,
        hub_page_id=hub_row.notion_page_id,
    )

    result = publisher.publish_report(report_data, str(report_file))

    # Record sync state
    sync_entry = NotionSyncState(
        entity_type="report",
        entity_key=report_file.name,
        notion_page_id=result["report_page_id"],
        notion_url=result.get("report_url"),
        source_report_path=str(report_file),
        metadata_json={"run_id": run_id, "topic_count": len(result.get("topic_pages", []))},
    )
    db.add(sync_entry)
    db.commit()
    logger.info("Notion auto-publish completed for run %s → %s", run_id, result["report_page_id"])
