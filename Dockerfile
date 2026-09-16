# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ARG PIP_INDEX_URL

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

# Keep third-party dependencies in a dedicated layer. Source-code changes
# will not invalidate this expensive network step.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip "setuptools>=68" wheel \
    && python -m pip install -r requirements.txt

# Copy application source only after dependencies are ready. The local package
# install resolves no dependencies, so normal source changes are fast to rebuild.
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY knowledge ./knowledge
COPY knowledge_seed ./knowledge_seed
COPY samples ./samples
COPY evals ./evals
RUN python -m pip install --no-build-isolation --no-deps .

# Celery warns when workers run as root. Use a dedicated unprivileged account
# while keeping /app writable for the local Chroma persistence directory.
RUN useradd --create-home --uid 10001 req2test \
    && mkdir -p /app/.req2test \
    && chown -R req2test:req2test /app
USER req2test

EXPOSE 8000

CMD ["python", "-m", "req2test.deploy"]
