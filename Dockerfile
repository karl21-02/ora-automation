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

COPY pyproject.toml /workspace/Ora/ora-automation/pyproject.toml
COPY README.md /workspace/Ora/ora-automation/README.md
COPY Makefile /workspace/Ora/ora-automation/Makefile
COPY src /workspace/Ora/ora-automation/src
COPY scripts /workspace/Ora/ora-automation/scripts
COPY automations /workspace/Ora/ora-automation/automations
COPY research_reports /workspace/Ora/ora-automation/research_reports

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
  && pip install -e .

WORKDIR /workspace/Ora/ora-automation
