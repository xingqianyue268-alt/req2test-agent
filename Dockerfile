FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /app

# Keep third-party dependencies in a dedicated Docker layer. Application source
# changes will no longer invalidate this expensive network/download step.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip "setuptools>=68" wheel \
    && python -m pip install --no-cache-dir -r requirements.txt

# Copy the project only after dependencies are installed, then install the local
# package without resolving dependencies again.
COPY pyproject.toml README.md ./
COPY src ./src
COPY knowledge ./knowledge
COPY samples ./samples
RUN python -m pip install --no-cache-dir --no-build-isolation --no-deps .

EXPOSE 8000

CMD ["uvicorn", "req2test.api:app", "--host", "0.0.0.0", "--port", "8000"]
