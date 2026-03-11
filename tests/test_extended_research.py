"""Tests for extended research sources (Phase F).

Tests cover:
- GitHub search
- HuggingFace search
- LLM-based source integration
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# GitHub Search Tests
# ---------------------------------------------------------------------------

class TestGitHubSearch:
    def test_search_repos_parses_response(self):
        from ora_rd_orchestrator.extended_research import search_github_repos

        mock_response = {
            "items": [
                {
                    "full_name": "owner/repo",
                    "name": "repo",
                    "description": "A test repository",
                    "html_url": "https://github.com/owner/repo",
                    "stargazers_count": 1000,
                    "forks_count": 100,
                    "language": "Python",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "topics": ["ai", "ml"],
                },
            ],
        }

        with patch("ora_rd_orchestrator.extended_research._request_json", return_value=mock_response):
            results = search_github_repos("test query", max_results=5)

        assert len(results) == 1
        assert results[0]["source"] == "github"
        assert results[0]["id"] == "owner/repo"
        assert results[0]["stars"] == 1000
        assert results[0]["url"] == "https://github.com/owner/repo"

    def test_search_repos_handles_error(self):
        from ora_rd_orchestrator.extended_research import search_github_repos

        with patch("ora_rd_orchestrator.extended_research._request_json", side_effect=Exception("Network error")):
            results = search_github_repos("test query")

        assert len(results) == 1
        assert "error" in results[0]

    def test_search_repos_respects_disabled_env(self):
        from ora_rd_orchestrator.extended_research import search_github_repos

        with patch.dict("os.environ", {"ORA_RD_GITHUB_SEARCH_ENABLED": "false"}):
            results = search_github_repos("test query")

        assert results == []


# ---------------------------------------------------------------------------
# HuggingFace Search Tests
# ---------------------------------------------------------------------------

class TestHuggingFaceSearch:
    def test_search_models_parses_response(self):
        from ora_rd_orchestrator.extended_research import search_huggingface_models

        mock_response = [
            {
                "modelId": "openai/whisper-large",
                "downloads": 50000,
                "likes": 1000,
                "pipeline_tag": "automatic-speech-recognition",
                "tags": ["pytorch", "whisper"],
                "lastModified": "2024-01-01T00:00:00Z",
            },
        ]

        with patch("ora_rd_orchestrator.extended_research._request_json", return_value=mock_response):
            results = search_huggingface_models("whisper", max_results=5)

        assert len(results) == 1
        assert results[0]["source"] == "huggingface"
        assert results[0]["source_type"] == "model"
        assert results[0]["id"] == "openai/whisper-large"
        assert results[0]["downloads"] == 50000
        assert results[0]["author"] == "openai"

    def test_search_datasets_parses_response(self):
        from ora_rd_orchestrator.extended_research import search_huggingface_datasets

        mock_response = [
            {
                "id": "mozilla-foundation/common_voice",
                "downloads": 100000,
                "likes": 500,
                "tags": ["speech", "audio"],
            },
        ]

        with patch("ora_rd_orchestrator.extended_research._request_json", return_value=mock_response):
            results = search_huggingface_datasets("speech", max_results=5)

        assert len(results) == 1
        assert results[0]["source_type"] == "dataset"
        assert results[0]["id"] == "mozilla-foundation/common_voice"

    def test_search_models_handles_error(self):
        from ora_rd_orchestrator.extended_research import search_huggingface_models

        with patch("ora_rd_orchestrator.extended_research._request_json", side_effect=Exception("API error")):
            results = search_huggingface_models("test")

        assert len(results) == 1
        assert "error" in results[0]


# ---------------------------------------------------------------------------
# Combined Search Tests
# ---------------------------------------------------------------------------

class TestCombinedSearch:
    def test_search_all_extended_sources(self):
        from ora_rd_orchestrator.extended_research import search_all_extended_sources

        github_response = {"items": [{"full_name": "test/repo", "name": "repo", "html_url": "https://github.com/test/repo", "stargazers_count": 100, "forks_count": 10}]}
        hf_models_response = [{"modelId": "test/model", "downloads": 1000}]
        hf_datasets_response = [{"id": "test/dataset", "downloads": 500}]

        def mock_request(url, *args, **kwargs):
            if "github.com" in url:
                return github_response
            elif "models" in url:
                return hf_models_response
            else:
                return hf_datasets_response

        with patch("ora_rd_orchestrator.extended_research._request_json", side_effect=mock_request):
            results = search_all_extended_sources("test query", max_results_per_source=3)

        assert "github_repos" in results
        assert "huggingface_models" in results
        assert "huggingface_datasets" in results
        assert len(results["github_repos"]) == 1
        assert len(results["huggingface_models"]) == 1


# ---------------------------------------------------------------------------
# LLM Integration Tests
# ---------------------------------------------------------------------------

class TestLLMIntegration:
    def test_integrate_research_sources_with_llm(self):
        from ora_rd_orchestrator.extended_research import integrate_research_sources
        from ora_rd_orchestrator.types import LLMResult

        academic_sources = [
            {"id": "arxiv:2401.00001", "title": "Paper 1", "url": "https://arxiv.org/abs/2401.00001"},
        ]
        extended_sources = {
            "github_repos": [
                {"id": "owner/repo", "title": "Implementation", "url": "https://github.com/owner/repo"},
            ],
        }

        mock_result = LLMResult(
            status="ok",
            parsed={
                "integrated_sources": [
                    {
                        "id": "arxiv:2401.00001",
                        "title": "Paper 1",
                        "url": "https://arxiv.org/abs/2401.00001",
                        "source_type": "arxiv",
                        "relevance_score": 0.9,
                        "related_sources": ["owner/repo"],
                        "summary": "Main research paper",
                    },
                    {
                        "id": "owner/repo",
                        "title": "Implementation",
                        "url": "https://github.com/owner/repo",
                        "source_type": "github",
                        "relevance_score": 0.85,
                        "related_sources": ["arxiv:2401.00001"],
                        "summary": "Code implementation",
                    },
                ],
                "duplicates_merged": [],
                "insights": [
                    {"insight": "Strong academic-practical connection", "supporting_sources": ["arxiv:2401.00001", "owner/repo"]},
                ],
                "topic_coverage": {
                    "academic": 0.8,
                    "practical": 0.7,
                    "gap_analysis": "Good coverage overall",
                },
            },
        )

        with patch("ora_rd_orchestrator.extended_research.run_llm_command", return_value=mock_result):
            result = integrate_research_sources(
                academic_sources=academic_sources,
                extended_sources=extended_sources,
                topic_name="test topic",
            )

        assert result["integration_status"] == "ok"
        assert len(result["integrated_sources"]) == 2
        assert len(result["insights"]) == 1

    def test_integrate_falls_back_on_llm_failure(self):
        from ora_rd_orchestrator.extended_research import integrate_research_sources
        from ora_rd_orchestrator.types import LLMResult

        academic_sources = [{"id": "1", "title": "Paper"}]
        extended_sources = {"github": [{"id": "2", "title": "Repo"}]}

        mock_result = LLMResult(status="failed", parsed={})

        with patch("ora_rd_orchestrator.extended_research.run_llm_command", return_value=mock_result):
            result = integrate_research_sources(
                academic_sources=academic_sources,
                extended_sources=extended_sources,
                topic_name="test",
            )

        assert result["integration_status"] == "fallback"
        assert len(result["integrated_sources"]) == 2  # Raw sources returned


# ---------------------------------------------------------------------------
# Comprehensive Research Tests
# ---------------------------------------------------------------------------

class TestComprehensiveResearch:
    def test_build_comprehensive_research(self):
        from ora_rd_orchestrator.extended_research import build_comprehensive_research
        from ora_rd_orchestrator.types import LLMResult

        academic_sources = [{"id": "arxiv:1", "title": "Paper 1"}]

        # Mock extended search
        github_response = {"items": []}
        hf_response = []

        mock_llm_result = LLMResult(
            status="ok",
            parsed={
                "integrated_sources": academic_sources,
                "duplicates_merged": [],
                "insights": [],
                "topic_coverage": {"academic": 0.8, "practical": 0.5, "gap_analysis": ""},
            },
        )

        with patch("ora_rd_orchestrator.extended_research._request_json", return_value=github_response):
            with patch("ora_rd_orchestrator.extended_research.run_llm_command", return_value=mock_llm_result):
                result = build_comprehensive_research(
                    topic_name="AI topic",
                    keywords=["keyword1", "keyword2"],
                    academic_sources=academic_sources,
                )

        assert result["topic"] == "AI topic"
        assert result["raw_academic_count"] == 1
        assert "integration" in result
