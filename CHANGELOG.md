# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-03-19

### Added
- Multi-agent R&D orchestration with scoring, debate, and consensus
- 24 YAML-based agent personas with Toss-style silo structure
- LangGraph 3-level convergence (Chapter → Silo → C-Level)
- FastAPI backend with REST API and SSE streaming
- React frontend with chatbot UI
- GitHub App integration for repository management
- Notion integration for report publishing
- DB-backed scheduler with cron and interval support
- Natural language scheduling via UPCE dialog engine
- Organization-aware pipeline with customizable agent structures
- Guest agent collaboration across organizations

### Infrastructure
- Docker Compose stack (9 services)
- PostgreSQL for persistence
- RabbitMQ for message routing
- APScheduler for background jobs

### Documentation
- Architecture documentation
- API reference
- Contributing guidelines
- Security policy

## [0.1.0] - 2024-12-01

### Added
- Initial release
- Basic R&D orchestration pipeline
- CLI interface
- Gemini LLM integration
