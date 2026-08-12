FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY knowledge ./knowledge
COPY samples ./samples

# Install build tooling explicitly, then disable PEP 517 build isolation for the
# local package. This avoids creating a second temporary build environment that
# needs to download setuptools/wheel again during Docker builds.
RUN python -m pip install --no-cache-dir --upgrade pip "setuptools>=68" wheel \
    && python -m pip install --no-cache-dir --no-build-isolation .

EXPOSE 8000

CMD ["uvicorn", "req2test.api:app", "--host", "0.0.0.0", "--port", "8000"]
