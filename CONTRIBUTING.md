# Contributing to Ora Automation

Thank you for your interest in contributing to Ora Automation! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- Docker & Docker Compose
- GCP account with Vertex AI enabled (for Gemini LLM)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/ora-automation.git
   cd ora-automation
   ```

2. **Set up Python environment**
   ```bash
   make setup
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Start services**
   ```bash
   make api-up
   ```

5. **Run tests**
   ```bash
   PYTHONPATH=src python3 -m pytest tests/ -v
   ```

## Development Workflow

### Branching Strategy

- `main` - Production-ready code
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation updates

### Making Changes

1. Create a new branch from `main`
2. Make your changes
3. Write/update tests
4. Ensure all tests pass
5. Submit a pull request

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(scheduler): add cron expression support
fix(clone-service): prevent race conditions
docs(readme): update installation instructions
```

## Code Standards

### Python

- Follow PEP 8
- Use type hints
- Write docstrings for public functions
- Keep functions focused and small

### TypeScript (Frontend)

- Use TypeScript strict mode
- Follow React best practices
- Use functional components with hooks

### Testing

- Write tests for new features
- Maintain test coverage
- Use descriptive test names

```bash
# Run Python tests
PYTHONPATH=src python3 -m pytest tests/ -v

# Type check frontend
cd frontend && npx tsc --noEmit
```

## Pull Request Process

1. **Title**: Use conventional commit format
2. **Description**: Explain what and why
3. **Tests**: Ensure all tests pass
4. **Review**: Wait for maintainer review

### PR Checklist

- [ ] Tests added/updated
- [ ] Documentation updated (if needed)
- [ ] No sensitive data in code
- [ ] Follows code standards
- [ ] Conventional commit message

## Project Structure

```
ora-automation/
├── src/
│   ├── ora_rd_orchestrator/    # Core R&D engine
│   └── ora_automation_api/     # FastAPI backend
├── frontend/                    # React frontend
├── tests/                       # Python tests
├── docs/                        # Documentation
└── docker-compose.yml          # Service stack
```

## Need Help?

- Check existing [issues](https://github.com/your-org/ora-automation/issues)
- Read the [documentation](docs/)
- Open a new issue for questions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
