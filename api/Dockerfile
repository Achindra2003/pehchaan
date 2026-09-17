FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY scripts ./scripts
RUN uv sync --frozen --no-dev && uv run python scripts/download_models.py

RUN useradd --create-home --uid 10001 pehchaan && chown -R pehchaan /app
USER pehchaan

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "pehchaan.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
