FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

# Dependencies first so code edits don't bust the layer cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn mogul.api.app:app --host 0.0.0.0 --port 8000"]
