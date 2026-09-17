FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY scripts ./scripts
RUN uv sync --frozen --no-dev && uv run python scripts/download_models.py

RUN useradd --create-home --uid 10001 pehchaan && chown -R pehchaan /app
USER pehchaan

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "pehchaan.main:app", "--host", "0.0.0.0", "--port", "8000"]
