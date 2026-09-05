FROM ghcr.io/astral-sh/uv:0.10.11 AS uv
FROM python:3.12.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY ai-service/app ./app
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["/workspace/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
