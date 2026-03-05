FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace/Ora/ora-automation

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    make \
    default-jre-headless \
    nodejs \
    npm \
  && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer cached unless pyproject.toml changes)
COPY pyproject.toml /workspace/Ora/ora-automation/pyproject.toml
COPY README.md /workspace/Ora/ora-automation/README.md

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
  && pip install -e . || true

# Then copy source and supporting files (changes frequently)
COPY src /workspace/Ora/ora-automation/src
COPY Makefile /workspace/Ora/ora-automation/Makefile
COPY scripts /workspace/Ora/ora-automation/scripts
COPY automations /workspace/Ora/ora-automation/automations
COPY research_reports /workspace/Ora/ora-automation/research_reports

# Re-install in editable mode now that src is present
RUN pip install --no-cache-dir -e .

WORKDIR /workspace/Ora/ora-automation
